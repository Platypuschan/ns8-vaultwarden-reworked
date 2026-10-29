//! NS8 admin session bridge. NS8 authorizes the open-admin action of the
//! module for the user running it, in that user's browser; the action
//! leaves a one-time ticket here. No NS8 credential reaches this server,
//! and the worker secret never leaves it.
use std::{collections::HashMap, fs, path::Path, sync::{LazyLock, Mutex}, time::{Duration, Instant, SystemTime, UNIX_EPOCH}};
use data_encoding::{BASE64URL_NOPAD, HEXLOWER};
use rocket::{form::Form, http::Status, request::{FromRequest, Outcome, Request}};
use serde_json::Value;
use crate::{crypto, CONFIG};

const COOKIE: &str = "NS8_ADMIN";
// Written by open-admin as <sha256 of the ticket>: {"user", "expires"}
const TICKETS: &str = "/ns8-admin-tickets";
const MAX_SESSIONS: usize = 256;

struct Session {
    user: String,
    // SHA-256 of the handle the module page keeps to renew the session
    handle: String,
    expires: Instant,
}

static SESSIONS: LazyLock<Mutex<HashMap<String, Session>>> = LazyLock::new(|| Mutex::new(HashMap::new()));

// A session ends this long after its last renewal. The module page renews
// it with a new ticket while it is open, so losing the right to run
// open-admin ends the admin access within this time.
static LIFETIME: LazyLock<Duration> = LazyLock::new(|| Duration::from_secs(
    std::env::var("NS8_ADMIN_SESSION_SECONDS").ok().and_then(|v| v.parse().ok()).unwrap_or(120)));

pub fn enabled() -> bool {
    std::env::var("NS8_MANAGED_CONFIG").as_deref() == Ok("true")
}

fn worker(request: &Request<'_>) -> bool {
    request.headers().get_one("X-NS8-Worker").is_some_and(super::validate_token)
}

pub struct Login {
    pub worker: bool,
    pub origin_allowed: bool,
}

#[rocket::async_trait]
impl<'r> FromRequest<'r> for Login {
    type Error = &'static str;
    async fn from_request(request: &'r Request<'_>) -> Outcome<Self, Self::Error> {
        let origin = request.headers().get_one("Origin").unwrap_or("");
        Outcome::Success(Self {
            worker: worker(request),
            origin_allowed: origin == CONFIG.domain_origin()
                || CONFIG.allowed_iframe_ancestors().split_whitespace().any(|allowed| allowed == origin),
        })
    }
}

fn well_formed(value: &str) -> bool {
    (32..=128).contains(&value.len()) && value.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}

/// Split "<ticket>:<handle>" and use the ticket: return its user and the
/// handle hash. A ticket works once, until it expires.
fn redeem(credential: &str) -> Option<(String, String)> {
    let (ticket, handle) = credential.split_once(':')?;
    if !well_formed(ticket) || !well_formed(handle) {
        return None;
    }
    let name = crypto::sha256_hex(ticket.as_bytes());
    let claimed = Path::new(TICKETS).join(format!("{name}.{}", crypto::encode_random_bytes::<8>(&HEXLOWER)));
    // Renaming is atomic: only one request can claim the ticket
    fs::rename(Path::new(TICKETS).join(&name), &claimed).ok()?;
    let data = fs::read(&claimed);
    fs::remove_file(&claimed).ok();
    let ticket: Value = serde_json::from_slice(&data.ok()?).ok()?;
    let now = SystemTime::now().duration_since(UNIX_EPOCH).ok()?.as_secs();
    if ticket["expires"].as_u64()? < now {
        return None;
    }
    let user = ticket["user"].as_str().filter(|user| !user.is_empty())?;
    Some((user.to_owned(), crypto::sha256_hex(handle.as_bytes())))
}

pub fn login(credential: &str) -> Option<String> {
    let (user, handle) = redeem(credential)?;
    let key = crypto::encode_random_bytes::<32>(&BASE64URL_NOPAD);
    let mut sessions = SESSIONS.lock().ok()?;
    let now = Instant::now();
    sessions.retain(|_, session| session.expires > now);
    if sessions.len() >= MAX_SESSIONS {
        return None;
    }
    sessions.insert(key.clone(), Session { user, handle, expires: now + *LIFETIME });
    Some(key)
}

/// Extend the session of the same user and handle; no cookie is needed,
/// so the module page also renews a session in another tab or site.
fn renew(credential: &str) -> bool {
    let Some((user, handle)) = redeem(credential) else { return false; };
    let Ok(mut sessions) = SESSIONS.lock() else { return false; };
    let now = Instant::now();
    sessions.retain(|_, session| session.expires > now);
    let mut renewed = false;
    for session in sessions.values_mut() {
        if crypto::ct_eq(&session.handle, &handle) && session.user == user {
            session.expires = now + *LIFETIME;
            renewed = true;
        }
    }
    renewed
}

#[derive(rocket::FromForm)]
pub struct RenewForm {
    token: String,
}

#[rocket::post("/ns8/renew", data = "<data>")]
pub fn renew_session(data: Form<RenewForm>, login: Login) -> Status {
    if !enabled() || !login.origin_allowed {
        return Status::Forbidden;
    }
    if renew(&data.token) { Status::NoContent } else { Status::Forbidden }
}

pub fn cookie_name() -> &'static str { COOKIE }

pub fn allowed(request: &Request<'_>) -> bool {
    if worker(request) { return true; }
    let Some(cookie) = request.cookies().get(COOKIE) else { return false; };
    let Ok(sessions) = SESSIONS.lock() else { return false; };
    sessions.get(cookie.value()).is_some_and(|session| session.expires > Instant::now())
}

pub fn denied<T>() -> Outcome<T, &'static str> {
    Outcome::Error((Status::Forbidden, "NS8 admin session missing or expired: open Vaultwarden again in the NS8 cluster manager"))
}

pub fn logout(cookies: &rocket::http::CookieJar<'_>) {
    if let Some(cookie) = cookies.get(COOKIE) {
        if let Ok(mut sessions) = SESSIONS.lock() { sessions.remove(cookie.value()); }
    }
    cookies.remove(rocket::http::Cookie::build(COOKIE).path(super::admin_path()));
}
