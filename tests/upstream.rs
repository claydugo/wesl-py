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
        let options = CompileOptions {
            keep: Some(vec!["selected".to_owned()]),
            features: Features {
                flags: [("enabled".to_owned(), Feature::Enable)].into(),
                ..Features::default()
            },
            ..CompileOptions::default()
        };
        let expected = wesl::compile(&"package::main".parse()?, &options, &resolver)?;
        let context = PyDict::new(py);
        context.set_item("wesl", py.import("wesl")?)?;
        context.set_item("modules", modules)?;
        let actual = py
            .eval(
                c"wesl.compile(modules, options=wesl.CompileOptions(keep=['selected'], features=wesl.Features(flags={'enabled': True}))).wgsl",
                Some(&context),
                None,
            )?
            .extract::<String>()?;
        assert_eq!(
            actual,
            expected.to_string(),
            "binding changes upstream output"
        );
        Ok(())
    })
}
