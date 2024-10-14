# Custom builds of LibCURL for pymcurl using binarybuilder.org 

This project builds custom binaries of the [LibCURL_jll.jl](https://github.com/JuliaBinaryWrappers/LibCURL_jll.jl/)
project for [pymcurl](https://github.com/genotrance/mcurl). The build has been modified to include `Kerberos_krb5`
on Linux and remove `LibSSH2` on all platforms.

## Building

This project relies on [Dev Containers](https://code.visualstudio.com/docs/remote/containers) to build the libraries.
A system supporting Docker is required for the build process. To build the libraries, follow these steps:

1. Install VSCode and set up the Remote SSH and Dev Containers extension
2. Add the Linux host to the SSH configuration within VSCode
3. Open a remote workspace on the Linux system using the Remote SSH extension
4. Checkout this project on the remote system
5. Use VSCode to open the folder in a Dev Container
6. Build the project by running the `build.sh` script

The build artifacts are created in the `build/L/LibCURL/Libcurl@8/products` directory.

### Specific version

A specific version of LibCURL can be built by specifying the version as an argument to the `build.sh` script:

```bash
./build.sh 8.9.0
```

The version needs to be a valid LibCURL version number mentioned in the `build/L/LibCURL/common.jl` file.

### Posting to GitHub

To post the built artifacts to a GitHub repository, run the `post.sh` script:

1. Script will prompt the user to update the version information in `Project.toml`
2. An updated `Artifacts.toml` will be generated based on artifacts and version info
3. Script will prompt the user to review both toml files and commit/push to GitHub
4. The final step will create a tag and and upload the build artifacts to the repository

The script will prompt the user to authenticate with GitHub to be able to post artifacts to this repository.
