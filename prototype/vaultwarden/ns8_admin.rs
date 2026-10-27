//! NS8 admin session bridge. The worker secret never leaves the server.
use std::{collections::HashMap, sync::{LazyLock, Mutex}, time::{Duration, Instant}};
use data_encoding::BASE64URL_NOPAD;
use rocket::{http::Status, request::{FromRequest, Outcome, Request}};
use serde_json::Value;
use crate::CONFIG;

const COOKIE: &str = "NS8_ADMIN";
static SESSIONS: LazyLock<Mutex<HashMap<String, (String, Instant)>>> = LazyLock::new(|| Mutex::new(HashMap::new()));

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

// Verify the NS8 token AND current cluster owner status. A JWT role claim or
// a successful GET is insufficient: NS8 authorizes roles only on mutations.
// list-users is read-only in effect; its supported task endpoint checks the
// current grants on the leader, and its result contains current owners only.
async fn authorize(token: &str) -> bool {
    async fn checked(token: &str) -> Option<()> {
        let base = std::env::var("NS8_CORE_API").ok()?;
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(5)).redirect(reqwest::redirect::Policy::none()).build().ok()?;
        let queued = client.post(format!("{base}/api/cluster/tasks"))
            .bearer_auth(token).json(&serde_json::json!({"action":"list-users","data":{},
                "extra":{"isNotificationHidden":true}}))
            .send().await.ok()?;
        if queued.status().as_u16() != 201 { return None; }
        let queued: Value = queued.json().await.ok()?;
        let task = queued["data"]["id"].as_str()?;
        // Decode identity only after the NS8 server accepted its signature.
        let claims = BASE64URL_NOPAD.decode(token.split('.').nth(1)?.as_bytes()).ok()?;
        let claims: Value = serde_json::from_slice(&claims).ok()?;
        let user = claims["id"].as_str()?;
        for _ in 0..30 {
            let response = client.get(format!("{base}/api/cluster/task/{task}/status"))
                .bearer_auth(token).send().await.ok()?;
            if response.status().is_success() {
                let result: Value = response.json().await.ok()?;
                if result["data"]["exit_code"].as_i64()? != 0 { return None; }
                let users = result["data"]["output"].as_array()?;
                return users.iter().any(|entry| entry["user"].as_str() == Some(user)).then_some(());
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        None
    }
    checked(token).await.is_some()
}

pub async fn login(token: &str) -> Option<String> {
    if !authorize(token).await { return None; }
    let key = crate::crypto::encode_random_bytes::<32>(&BASE64URL_NOPAD);
    let mut sessions = SESSIONS.lock().ok()?;
    sessions.retain(|_, (_, created)| created.elapsed() < Duration::from_secs(43200));
    if sessions.len() >= 4096 { return None; }
    sessions.insert(key.clone(), (token.to_owned(), Instant::now()));
    Some(key)
}

pub fn cookie_name() -> &'static str { COOKIE }

pub async fn allowed(request: &Request<'_>) -> bool {
    if worker(request) { return true; }
    let Some(cookie) = request.cookies().get(COOKIE) else { return false; };
    let token = SESSIONS.lock().ok().and_then(|sessions| sessions.get(cookie.value())
        .filter(|(_, created)| created.elapsed() < Duration::from_secs(43200))
        .map(|(token, _)| token.clone()));
    let Some(token) = token else { return false; };
    if authorize(&token).await { return true; }
    if let Ok(mut sessions) = SESSIONS.lock() { sessions.remove(cookie.value()); }
    false
}

pub fn denied<T>() -> Outcome<T, &'static str> {
    Outcome::Error((Status::Forbidden, "Current NS8 cluster administrator rights required"))
}

pub fn logout(cookies: &rocket::http::CookieJar<'_>) {
    if let Some(cookie) = cookies.get(COOKIE) {
        if let Ok(mut sessions) = SESSIONS.lock() { sessions.remove(cookie.value()); }
    }
    cookies.remove(rocket::http::Cookie::build(COOKIE).path(super::admin_path()));
}
