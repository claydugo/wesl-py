use std::{env, fs, path::PathBuf, process::Command};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("cargo:rerun-if-changed=Cargo.lock");
    println!("cargo:rerun-if-changed=Cargo.toml");
    println!("cargo:rerun-if-changed=src/lib.rs");
    println!("cargo:rerun-if-env-changed=WESL_PY_BUILD_REVISION");
    let lock: toml::Table = fs::read_to_string("Cargo.lock")?.parse()?;
    let compiler = lock["package"]
        .as_array()
        .ok_or("locked packages")?
        .iter()
        .find(|package| package["name"].as_str() == Some("wesl"))
        .ok_or("locked WESL dependency")?;
    let version = compiler["version"].as_str().ok_or("compiler version")?;
    println!("cargo:rustc-env=WESL_COMPILER_VERSION={version}");
    let manifest: toml::Table = fs::read_to_string("Cargo.toml")?.parse()?;
    let revision = env::var("WESL_PY_BUILD_REVISION").ok();
    let rustc = Command::new(env::var_os("RUSTC").ok_or("Rust compiler")?)
        .arg("--version")
        .output()?;
    let metadata = serde_json::json!({
        "binding_version": env::var("CARGO_PKG_VERSION")?,
        "binding_revision": revision,
        "compiler_version": version,
        "compiler_source": compiler["source"].as_str(),
        "compiler_revision": manifest["package"]["metadata"]["wesl"]["revision"].as_str(),
        "compiler_features": manifest["dependencies"]["wesl"].get("features")
            .cloned().unwrap_or_else(|| toml::Value::Array(Vec::new())),
        "target": env::var("TARGET")?,
        "rustc": String::from_utf8_lossy(&rustc.stdout).trim(),
    });
    fs::write(
        PathBuf::from(env::var_os("OUT_DIR").ok_or("build output")?).join("build-metadata.json"),
        metadata.to_string(),
    )?;
    Ok(())
}
