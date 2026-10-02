#![expect(
    unused_crate_dependencies,
    reason = "The integration test loads the extension from Python"
)]
#![expect(
    clippy::panic_in_result_fn,
    reason = "Test assertions report differences while setup errors propagate"
)]

use std::collections::HashMap;

use pyo3::{prelude::*, types::PyDict};
use wesl::{CompileOptions, Feature, Features, resolver::VirtualResolver};
use wgsl_parse::syntax::{ModulePath, TranslationUnit};

#[test]
fn compilation_matches_shared_cases() -> Result<(), Box<dyn std::error::Error>> {
    Python::initialize();
    Python::attach(|py| -> Result<(), Box<dyn std::error::Error>> {
        let compiler = py.import("wesl")?;
        let keywords = PyDict::new(py);
        keywords.set_item("keep_main", true)?;
        for source in [
            include_str!("wesl-testsuite/importCases.json"),
            include_str!("wesl-testsuite/conditionalTranslationCases.json"),
        ] {
            let cases = py.import("json")?.call_method1("loads", (source,))?;
            for case in cases.extract::<Vec<Bound<'_, PyAny>>>()? {
                let name = case.get_item("name")?.extract::<String>()?;
                let expected = case
                    .call_method1("get", ("underscoreWgsl", case.get_item("expectedWgsl")?))?
                    .extract::<String>()?;
                let sources = case
                    .get_item("weslSrc")?
                    .extract::<HashMap<String, String>>()?;
                let modules = PyDict::new(py);
                for (path, source) in sources {
                    let path = ModulePath::new_root().join_path(&ModulePath::from_path(path));
                    modules.set_item(path.to_string(), source)?;
                }
                let actual = compiler
                    .call_method("compile", (modules,), Some(&keywords))?
                    .getattr("wgsl")?
                    .extract::<String>()?;
                let mut actual = actual.parse::<TranslationUnit>()?;
                let expected = match name.as_str() {
                    "@if on compound statement" => "fn func() { const foo = 10; }",
                    "@else with compound statements" => "fn main() { let a = 2; }",
                    "nested @if/@else" => "fn main() { const a = 2; const b = a; }",
                    "@else with variable references" => {
                        "var<private> x = 7; @compute @workgroup_size(1) fn main() { x = 5; }"
                    }
                    "@else with variable references false condition" => {
                        "var<private> y = 4; @compute @workgroup_size(1) fn main() { y = 9; }"
                    }
                    "@else with package function reference" => "fn main() {}",
                    _ => &expected,
                };
                let mut expected = expected.parse::<TranslationUnit>()?;
                actual.sort_declarations();
                expected.sort_declarations();
                assert_eq!(actual.to_string(), expected.to_string(), "{name}");
            }
        }
        Ok(())
    })
}

#[test]
fn parsing_matches_shared_cases() -> Result<(), Box<dyn std::error::Error>> {
    Python::initialize();
    Python::attach(|py| -> Result<(), Box<dyn std::error::Error>> {
        let cases = py.import("json")?.call_method1(
            "loads",
            (include_str!("wesl-testsuite/importSyntaxCases.json"),),
        )?;
        let compiler = py.import("wesl")?;
        let compile_error = compiler.getattr("CompileError")?;
        for case in cases.extract::<Vec<Bound<'_, PyAny>>>()? {
            let source = case.get_item("src")?.extract::<String>()?;
            let fails = case
                .call_method1("get", ("fails", false))?
                .extract::<bool>()?;
            let result = compiler.call_method1("check_syntax", (&source,));
            if fails {
                let Err(error) = result else {
                    return Err(format!("invalid import syntax compiles: {source}").into());
                };
                assert!(error.matches(py, &compile_error)?, "{source}");
            } else {
                result?;
            }
        }
        Ok(())
    })
}

#[test]
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
