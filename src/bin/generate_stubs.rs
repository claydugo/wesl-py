use pyo3 as _;
use wesl as _;
use wesl_quote as _;
use wgsl_parse as _;

fn main() -> pyo3_stub_gen::Result<()> {
    let stub = _native::stub_info()?;
    let module = stub
        .modules
        .get("wesl._native")
        .ok_or_else(|| std::io::Error::other("missing native module"))?;
    let source = module.format_with_config(false);
    let source = source
        .splitn(3, '\n')
        .nth(2)
        .ok_or_else(|| std::io::Error::other("missing stub header"))?;
    std::fs::write(stub.python_root.join("wesl/_native.pyi"), source)?;
    Ok(())
}
