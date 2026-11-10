import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const cacheRequire = createRequire(require.resolve("flat-cache"));
const editorRequire = createRequire(require.resolve("external-editor"));
const gypRequire = createRequire(require.resolve("node-gyp/package.json"));

test("node-gyp resolves patched undici with its download request API", async () => {
  const version = gypRequire("undici/package.json").version;
  assert.ok(
    version.startsWith("8.") &&
      (Number(version.split(".")[1]) > 12 ||
        (Number(version.split(".")[1]) === 12 &&
          Number(version.split(".")[2]) >= 2)),
    version
  );
  const { createServer } = require("node:http");
  const server = createServer((request, response) => response.end("download"));
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const { statusCode, body } = await gypRequire("undici").request(
      `http://127.0.0.1:${server.address().port}/headers`
    );
    assert.equal(statusCode, 200);
    assert.equal(await body.text(), "download");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("external-editor uses fixed tmp and retains file creation/cleanup", () => {
  const version = editorRequire("tmp/package.json").version;
  assert.ok(
    version.startsWith("0.2.") && Number(version.split(".")[2]) >= 6,
    version
  );
  const { ExternalEditor } = require("external-editor");
  const editor = new ExternalEditor("preserved", { tmpdir: tmpdir() });
  try {
    assert.equal(
      require("node:fs").readFileSync(editor.tempFile, "utf8"),
      "preserved"
    );
  } finally {
    editor.cleanup();
  }
  assert.equal(require("node:fs").existsSync(editor.tempFile), false);
});

test("flat-cache uses fixed flatted and preserves cyclic cache data", () => {
  const version = cacheRequire("flatted/package.json").version;
  assert.ok(
    Number(version.split(".")[0]) === 3 &&
      Number(version.split(".")[1]) >= 4 &&
      version !== "3.4.0" &&
      version !== "3.4.1",
    version
  );
  const directory = mkdtempSync(join(tmpdir(), "vw-cache-"));
  try {
    const cache = require("flat-cache").create("regression", directory);
    const value = { label: "preserved" };
    value.self = value;
    cache.setKey("value", value);
    cache.save(true);
    const restored = require("flat-cache")
      .create("regression", directory)
      .getKey("value");
    assert.equal(restored.label, "preserved");
    assert.equal(restored.self, restored);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
