use std::{
    collections::{HashMap, HashSet},
    sync::LazyLock,
};

use wesl::{
    CompileOptions, CompileResult, Error, Mangler, Resolver,
    error::UsageError,
    pass::{self, CompilerDriver, Module, UsedItems, Visit},
    sourcemap::SourceMapper,
};
use wgsl_parse::SyntaxNode;
use wgsl_parse::syntax::{
    GlobalDeclaration, Ident, ImportContent, ModulePath, PathOrigin, TranslationUnit,
    TypeExpression, Visibility,
};

pub(super) fn clone_syntax(syntax: &TranslationUnit) -> TranslationUnit {
    let mut syntax = syntax.clone();
    let mut pending: Vec<_> = syntax.global_declarations.iter_mut().collect();
    while let Some(declaration) = pending.pop() {
        let ident = match &mut **declaration {
            GlobalDeclaration::Declaration(declaration) => &mut declaration.ident,
            GlobalDeclaration::TypeAlias(alias) => &mut alias.ident,
            GlobalDeclaration::Struct(structure) => &mut structure.ident,
            GlobalDeclaration::Function(function) => &mut function.ident,
            GlobalDeclaration::Compound(compound) => {
                pending.extend(&mut compound.body);
                continue;
            }
            GlobalDeclaration::Void | GlobalDeclaration::ConstAssert(_) => continue,
        };
        *ident = Ident::new(ident.to_string());
    }
    syntax
}

pub(super) fn load_module(
    path: &ModulePath,
    resolver: &impl Resolver,
) -> Result<TranslationUnit, Error> {
    let source = resolver.resolve_source(path)?;
    if matches!(&path.origin, PathOrigin::Package(name) if name == "wgsl_test") {
        if path.components.is_empty()
            && source == include_str!("../python/wesl/shaders/wgsl_test/package.wesl")
        {
            static SYNTAX: LazyLock<Option<TranslationUnit>> = LazyLock::new(|| {
                include_str!("../python/wesl/shaders/wgsl_test/package.wesl")
                    .parse()
                    .ok()
            });
            if let Some(syntax) = &*SYNTAX {
                return Ok(clone_syntax(syntax));
            }
        } else if path.components == ["TestResult"]
            && source == include_str!("../python/wesl/shaders/wgsl_test/TestResult.wesl")
        {
            static SYNTAX: LazyLock<Option<TranslationUnit>> = LazyLock::new(|| {
                include_str!("../python/wesl/shaders/wgsl_test/TestResult.wesl")
                    .parse()
                    .ok()
            });
            if let Some(syntax) = &*SYNTAX {
                return Ok(clone_syntax(syntax));
            }
        }
    }
    source.parse().map_err(|error| {
        wesl::error::Diagnostic::from(error)
            .with_module_path(path.clone(), resolver.display_name(path))
            .with_source(source.to_string())
            .into()
    })
}

struct Driver<'a, Transform> {
    main_path: &'a ModulePath,
    options: &'a CompileOptions,
    resolver: &'a dyn Resolver,
    mangler: &'a dyn Mangler,
    parsed_modules: HashMap<ModulePath, TranslationUnit>,
    transform: Transform,
}

impl<Transform> CompilerDriver for Driver<'_, Transform>
where
    Transform: FnMut(&ModulePath, &mut TranslationUnit) -> Result<(), Error>,
{
    fn main_path(&self) -> &ModulePath {
        self.main_path
    }

    fn canonical_path(&self, path: &ModulePath) -> ModulePath {
        self.resolver.canonical_path(path)
    }

    fn main_entry_points(&self, module: &TranslationUnit) -> Result<HashSet<Ident>, Error> {
        if !self.options.strip || self.options.keep_main {
            Ok(module
                .global_declarations
                .iter()
                .filter_map(SyntaxNode::ident)
                .collect())
        } else if let Some(keep) = &self.options.keep {
            if keep.len() <= 1 {
                return keep
                    .iter()
                    .map(|name| {
                        module
                            .global_declarations
                            .iter()
                            .filter_map(SyntaxNode::ident)
                            .find(|ident| *ident.name() == *name)
                            .ok_or_else(|| {
                                UsageError::NotFound(self.main_path.clone(), name.clone()).into()
                            })
                    })
                    .collect();
            }
            let mut declarations = HashMap::new();
            for ident in module
                .global_declarations
                .iter()
                .filter_map(SyntaxNode::ident)
            {
                let name = ident.name().to_string();
                declarations.entry(name).or_insert(ident);
            }
            keep.iter()
                .map(|name| {
                    declarations.get(name).cloned().ok_or_else(|| {
                        UsageError::NotFound(self.main_path.clone(), name.clone()).into()
                    })
                })
                .collect()
        } else {
            Ok(pass::main_entry_points(module))
        }
    }

    fn module_usage_analysis(
        &self,
        module: &Module,
        already_used: &mut UsedItems,
        to_analyze: &mut UsedItems,
    ) -> Result<(), Error> {
        pass::module_usage_analysis(module, already_used, to_analyze, !self.options.visibility)?;
        if !self.options.strip {
            for declaration in &module.syntax.global_declarations {
                if let Some(ident) = declaration.ident() {
                    self.usage_analysis(
                        module,
                        &ident.name(),
                        declaration.visibility(),
                        already_used,
                        to_analyze,
                    )?;
                }
            }
        }
        if !self.options.imports {
            *to_analyze = UsedItems::new();
        }
        Ok(())
    }

    fn usage_analysis(
        &self,
        module: &Module,
        name: &str,
        minimum_visibility: Visibility,
        already_used: &mut UsedItems,
        to_analyze: &mut UsedItems,
    ) -> Result<(), Error> {
        pass::usage_analysis(
            module,
            name,
            if self.options.visibility {
                minimum_visibility
            } else {
                Visibility::Private
            },
            already_used,
            to_analyze,
            !self.options.visibility,
        )?;
        if !self.options.imports {
            *to_analyze = UsedItems::new();
        }
        Ok(())
    }

    fn load_module(&mut self, path: &ModulePath) -> Result<TranslationUnit, Error> {
        let mut module = if let Some(module) = self.parsed_modules.remove(path) {
            if self.options.sourcemap {
                self.resolver.resolve_source(path)?;
            }
            module
        } else {
            load_module(path, &self.resolver)?
        };
        if matches!(&path.origin, PathOrigin::Package(_)) {
            for import in &mut module.imports {
                if import.path.is_none()
                    && let ImportContent::Collection(collection) = &mut import.content
                {
                    for item in collection {
                        if let Some(name) = item.path.first_mut() {
                            *name = path
                                .join_path(&ModulePath::new(
                                    PathOrigin::Package(name.clone()),
                                    Vec::new(),
                                ))
                                .to_string();
                        }
                    }
                }
            }
        }
        (self.transform)(path, &mut module)?;
        if self.options.condcomp {
            pass::condcomp(&mut module, &self.options.features).map_err(|error| {
                error
                    .diagnostic()
                    .with_module_path(path.clone(), self.resolver.display_name(path))
            })?;
        }
        pass::retarget_idents(&mut module);
        Visit::<TypeExpression>::visit_rec_mut(&mut module, &mut |expression| {
            if expression.path.is_some() {
                expression.ident = Ident::new(expression.ident.to_string());
            }
        });
        if self.options.validate {
            pass::validate_wesl(&module).map_err(|error| {
                error.with_module_path(path.clone(), self.resolver.display_name(path))
            })?;
        }
        Ok(module)
    }

    fn link(
        &self,
        modules: &mut Vec<Module>,
        used_items: &UsedItems,
    ) -> Result<TranslationUnit, Error> {
        if self.options.imports {
            pass::retarget_modules(modules, used_items, &self.resolver);
        } else {
            for module in modules.iter_mut() {
                Visit::<TypeExpression>::visit_rec_mut(&mut module.syntax, &mut |expression| {
                    expression.path = None;
                });
            }
        }
        for module in modules.iter_mut() {
            if self.options.mangle_main || module.path != *self.main_path {
                pass::mangle(&mut module.syntax, &module.path, &self.mangler);
            }
        }
        let module = pass::link(modules, self.options.strip.then_some(used_items));
        if self.options.validate {
            pass::validate_wgsl(&module)?;
        }
        Ok(module)
    }
}

pub(super) fn compile(
    main_path: &ModulePath,
    options: &CompileOptions,
    resolver: &impl Resolver,
    parsed_modules: HashMap<ModulePath, TranslationUnit>,
    transform: impl FnMut(&ModulePath, &mut TranslationUnit) -> Result<(), Error>,
) -> Result<CompileResult, Error> {
    let mangler = Box::<dyn Mangler>::from(options.mangler);
    let mapper = SourceMapper::new(main_path.clone(), resolver, &mangler);
    let result = Driver {
        main_path,
        options,
        resolver: if options.sourcemap { &mapper } else { resolver },
        mangler: if options.sourcemap { &mapper } else { &mangler },
        parsed_modules,
        transform,
    }
    .compile();
    let sourcemap = options.sourcemap.then(|| mapper.finish());
    let result = result.map_err(|error| error.diagnostic().with_sourcemap(&sourcemap))?;
    Ok(CompileResult {
        syntax: result.syntax,
        modules: result.modules,
        used_items: result.used_items,
        sourcemap,
    })
}
