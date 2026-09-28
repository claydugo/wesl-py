#![expect(
    unused_crate_dependencies,
    reason = "The integration test loads the extension from Python"
)]

use pyo3::{prelude::*, types::PyDict};
use wesl::{CompileOptions, Feature, Features, resolver::VirtualResolver};
use wgsl_parse::syntax::ModulePath;

#[test]
#[expect(
    clippy::panic_in_result_fn,
    reason = "Test assertions report differences while setup errors propagate"
)]
fn compilation_matches_upstream() -> Result<(), Box<dyn std::error::Error>> {
    Python::initialize();
    Python::attach(|py| -> Result<(), Box<dyn std::error::Error>> {
        let modules = PyDict::new(py);
        let mut resolver = VirtualResolver::new();
        for (path, source) in [
            (
                "package::main",
                "import package::helper::value; \
                 fn selected() -> u32 { return value(); } fn unused() {}",
            ),
            (
                "package::helper",
                "@if(enabled) fn value() -> u32 { return 7u; } \
                 @if(!enabled) fn value() -> u32 { return 3u; }",
            ),
        ] {
            modules.set_item(path, source)?;
            resolver.add_module(path.parse::<ModulePath>()?, source.into());
        }
        let context = PyDict::new(py);
        context.set_item("wesl", py.import("wesl")?)?;
        context.set_item("modules", modules)?;
        for (strip, keep_main, mangle_main, visibility, sourcemap) in [
            (true, false, false, false, true),
            (true, false, true, true, false),
            (true, true, false, true, true),
            (false, false, true, false, true),
        ] {
            let options = CompileOptions {
                strip,
                keep_main,
                mangle_main,
                visibility,
                sourcemap,
                keep: Some(vec!["selected".to_owned()]),
                features: Features {
                    flags: [("enabled".to_owned(), Feature::Enable)].into(),
                    ..Features::default()
                },
                ..CompileOptions::default()
            };
            let expected = wesl::compile(&"package::main".parse()?, &options, &resolver)?;
            context.set_item("strip", strip)?;
            context.set_item("keep_main", keep_main)?;
            context.set_item("mangle_main", mangle_main)?;
            context.set_item("visibility", visibility)?;
            context.set_item("sourcemap", sourcemap)?;
            let actual = py
                .eval(
                    c"wesl.compile(modules, options=wesl.CompileOptions(strip=strip, keep_main=keep_main, mangle_main=mangle_main, visibility=visibility, sourcemap=sourcemap, keep=['selected'], features=wesl.Features(flags={'enabled': True}))).wgsl",
                    Some(&context),
                    None,
                )?
                .extract::<String>()?;
            assert_eq!(actual, expected.to_string(), "WGSL differs");
        }
        Ok(())
    })
}
