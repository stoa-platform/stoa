fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("cargo:rerun-if-changed=proto");
    let descriptors = protox::Compiler::new(["proto"])?
        .include_imports(true)
        .include_source_info(true)
        .open_file("envoy/service/auth/v3/external_auth.proto")?
        .encode_file_descriptor_set();
    let path = std::path::PathBuf::from(std::env::var("OUT_DIR")?).join("envoy.bin");
    std::fs::write(&path, descriptors)?;
    // protox 0.10 produces prost 0.14 descriptors. The encoded descriptor set
    // is wire compatible with tonic-build 0.12 / prost 0.13. Never run protoc.
    tonic_build::configure()
        .include_file("envoy.rs")
        .file_descriptor_set_path(path)
        .skip_protoc_run()
        .compile_protos(
            &["proto/envoy/service/auth/v3/external_auth.proto"],
            &["proto"],
        )?;
    Ok(())
}
