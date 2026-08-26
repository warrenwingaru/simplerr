{
    inputs = {
        nixpkgs-22.url = "github:NixOS/nixpkgs/22.05";
        nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
        flake-utils.url = "github:numtide/flake-utils";
      };
    outputs = inputs@{ flake-utils, ... }:
      flake-utils.lib.eachDefaultSystem(system:
          let
            pkgs = (import inputs.nixpkgs-unstable { inherit system;});
            pkgs22 = (import inputs.nixpkgs-22 {inherit system;});
          in
          {
            devShell = pkgs.mkShell {
                buildInputs = [
                    pkgs22.python39
                ];

                shellHook = ''
                '';
              };
            }
        );
  }
