#!/usr/bin/env python3
"""Diagnostico do ambiente de build nativo do desktop (Tauri + whisper-rs).

Nao instala nada. Nao escreve em lugar nenhum. So olha a maquina, diz o que
falta para `npm run tauri dev`/`build` compilar, e imprime o comando exato que
resolve cada ausencia.

Contexto: desde o PR #63 o `desktop/src-tauri` depende de `whisper-rs`, que
compila o whisper.cpp com **CMake** e gera os bindings com **bindgen**, que por
sua vez precisa de uma **libclang**. Nenhum dos dois vem com o rustup, e a
falha de cada um acontece dentro de um build script — a mensagem sai longe do
que o usuario fez. Este script antecipa as duas.

Nada disso e necessario para `npm test` (vitest): o vitest roda modulo puro,
sem tocar na toolchain Rust.

Exit code: 0 quando tudo que o build precisa esta presente, 1 quando falta algo.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

WINDOWS = sys.platform == "win32"

# Nomes da biblioteca do clang que o bindgen procura, por plataforma.
NOMES_LIBCLANG = (
    ("libclang.dll", "clang.dll")
    if WINDOWS
    else ("libclang.dylib",)
    if sys.platform == "darwin"
    else ("libclang.so", "libclang.so.1")
)


@dataclass
class Resultado:
    """O veredito de um item do ambiente."""

    nome: str
    ok: bool
    detalhe: str
    # Comando (ou passo) que resolve, quando nao esta ok.
    como_resolver: list[str] = field(default_factory=list)
    # Variavel de ambiente a exportar, quando o item foi achado fora do PATH.
    export: tuple[str, str] | None = None


def _versao(executavel: str, *args: str) -> str:
    """Primeira linha do `--version`, ou string vazia se nao rodar."""
    try:
        saida = subprocess.run(
            [executavel, *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    linhas = (saida.stdout or saida.stderr).strip().splitlines()
    return linhas[0].strip() if linhas else ""


def checar_rust() -> Resultado:
    cargo = shutil.which("cargo")
    if cargo:
        return Resultado("cargo (rustup)", True, f"{cargo} - {_versao(cargo, '--version')}")
    return Resultado(
        "cargo (rustup)",
        False,
        "nao encontrado no PATH",
        ["Instale a toolchain Rust: https://rustup.rs"],
    )


def checar_node() -> Resultado:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm:
        return Resultado("npm (Node.js)", True, f"{npm} - v{_versao(npm, '--version')}")
    return Resultado(
        "npm (Node.js)",
        False,
        "nao encontrado no PATH",
        ["Instale o Node.js 20+: https://nodejs.org"],
    )


def _cmake_do_visual_studio() -> list[Path]:
    """CMake que vem embutido no Visual Studio / Build Tools 2022 (Windows).

    Ele existe na maioria das maquinas que ja tem o MSVC (obrigatorio para o
    Tauri), mas **nao entra no PATH** — e a causa mais comum do
    "is `cmake` not installed?" em quem acha que nao instalou CMake nenhum.
    """
    if not WINDOWS:
        return []
    raizes = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    achados: list[Path] = []
    for raiz in raizes:
        padrao = os.path.join(
            raiz,
            "Microsoft Visual Studio",
            "*",
            "*",
            "Common7",
            "IDE",
            "CommonExtensions",
            "Microsoft",
            "CMake",
            "CMake",
            "bin",
            "cmake.exe",
        )
        achados.extend(Path(p) for p in glob.glob(padrao))
    return sorted(achados)


def checar_cmake() -> Resultado:
    # 1) A variavel CMAKE tem precedencia no crate `cmake` usado pelo build
    #    script do whisper-rs-sys.
    do_env = os.environ.get("CMAKE")
    if do_env and Path(do_env).is_file():
        return Resultado("cmake", True, f"CMAKE={do_env} - {_versao(do_env, '--version')}")

    # 2) PATH.
    no_path = shutil.which("cmake")
    if no_path:
        return Resultado("cmake", True, f"{no_path} - {_versao(no_path, '--version')}")

    # 3) Embutido no Visual Studio: existe, mas o build nao acha sozinho.
    embutidos = _cmake_do_visual_studio()
    if embutidos:
        escolhido = embutidos[-1]
        return Resultado(
            "cmake",
            False,
            f"fora do PATH, mas existe no Visual Studio: {escolhido}",
            [
                "Aponte a variavel CMAKE para ele (ou acrescente a pasta ao PATH) - "
                "veja --exports"
            ],
            export=("CMAKE", str(escolhido)),
        )

    return Resultado(
        "cmake",
        False,
        "nao encontrado (nem no PATH, nem em CMAKE, nem no Visual Studio)",
        (
            ["winget install Kitware.CMake"]
            if WINDOWS
            else ["Instale o cmake pelo gerenciador de pacotes do sistema"]
        ),
    )


def _tem_libclang(pasta: Path) -> Path | None:
    for nome in NOMES_LIBCLANG:
        alvo = pasta / nome
        if alvo.is_file():
            return alvo
    return None


def _libclang_do_llvm() -> list[Path]:
    """LLVM instalado no sistema — o caminho recomendado, quando existe."""
    candidatos: list[Path] = []
    if WINDOWS:
        for raiz in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ):
            candidatos.append(Path(raiz) / "LLVM" / "bin")
    else:
        candidatos += [Path("/usr/lib"), Path("/usr/local/lib"), Path("/opt/homebrew/lib")]
    return [p for p in candidatos if p.is_dir() and _tem_libclang(p)]


def _libclang_de_wheel_pip() -> list[Path]:
    """Wheel `libclang` do pip, em qualquer Python que esteja visivel.

    Varre o Python que roda este script e **todos** os `python` do PATH, nao so
    o primeiro: quem roda isto de dentro de um venv veria apenas o venv, e a
    wheel costuma estar no Python de usuario, mais atras no PATH. E o caminho
    sem privilegio de administrador, ao custo de amarrar o build a um
    site-packages.
    """
    pythons: list[str] = [sys.executable]
    nomes = ("python.exe", "python3.exe") if WINDOWS else ("python", "python3")
    for pasta_path in os.environ.get("PATH", "").split(os.pathsep):
        if not pasta_path:
            continue
        for nome in nomes:
            candidato = Path(pasta_path) / nome
            # O WindowsApps traz stubs que so abrem a loja; ignorar.
            if "WindowsApps" in str(candidato):
                continue
            if candidato.is_file() and str(candidato) not in pythons:
                pythons.append(str(candidato))

    achados: list[Path] = []
    for py in pythons:
        try:
            saida = subprocess.run(
                [py, "-c", "import clang, os; print(os.path.dirname(clang.__file__))"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if saida.returncode != 0:
            continue
        pasta = Path(saida.stdout.strip()) / "native"
        if pasta.is_dir() and _tem_libclang(pasta) and pasta not in achados:
            achados.append(pasta)
    return achados


def checar_libclang() -> Resultado:
    # 1) A variavel que o bindgen le. Se estiver setada e valida, acabou.
    do_env = os.environ.get("LIBCLANG_PATH")
    if do_env:
        pasta = Path(do_env)
        alvo = _tem_libclang(pasta) if pasta.is_dir() else (pasta if pasta.is_file() else None)
        if alvo:
            return Resultado("libclang (bindgen)", True, f"LIBCLANG_PATH={do_env} -> {alvo.name}")
        return Resultado(
            "libclang (bindgen)",
            False,
            f"LIBCLANG_PATH={do_env} aponta para um lugar sem {'/'.join(NOMES_LIBCLANG)}",
            ["Corrija ou limpe a variavel e rode este script de novo"],
        )

    # 2) LLVM de sistema — nao precisa de variavel nenhuma se estiver no lugar
    #    padrao, mas apontar LIBCLANG_PATH e mais previsivel.
    for pasta in _libclang_do_llvm():
        return Resultado(
            "libclang (bindgen)",
            False,
            f"LLVM instalado em {pasta}, mas LIBCLANG_PATH nao esta setada",
            ["Exporte LIBCLANG_PATH - veja --exports"],
            export=("LIBCLANG_PATH", str(pasta)),
        )

    # 3) Wheel do pip.
    for pasta in _libclang_de_wheel_pip():
        return Resultado(
            "libclang (bindgen)",
            False,
            f"wheel `libclang` do pip encontrada em {pasta}, mas LIBCLANG_PATH nao esta setada",
            ["Exporte LIBCLANG_PATH - veja --exports"],
            export=("LIBCLANG_PATH", str(pasta)),
        )

    return Resultado(
        "libclang (bindgen)",
        False,
        "nenhuma libclang na maquina (sem LLVM de sistema, sem wheel do pip)",
        (
            [
                "winget install LLVM.LLVM      # recomendado; precisa de admin e ~3 GB",
                "python -m pip install libclang # alternativa sem admin",
            ]
            if WINDOWS
            else ["Instale o pacote libclang-dev (ou equivalente) do sistema"]
        ),
    )


def montar_exports(resultados: list[Resultado]) -> list[tuple[str, str]]:
    return [r.export for r in resultados if r.export]


def imprimir_exports(exports: list[tuple[str, str]]) -> None:
    if not exports:
        print("Nada a exportar - o que falta nao esta na maquina ainda.")
        return
    print("PowerShell (so esta sessao):")
    for nome, valor in exports:
        print(f'  $env:{nome} = "{valor}"')
    print()
    print("PowerShell (permanente, sobrevive ao reboot):")
    for nome, valor in exports:
        print(f'  [Environment]::SetEnvironmentVariable("{nome}", "{valor}", "User")')
    print()
    print("Git Bash (so esta sessao):")
    for nome, valor in exports:
        print(f"  export {nome}='{valor}'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnostica o ambiente de build nativo do desktop (Tauri + whisper-rs). "
            "So le a maquina: nao instala e nao altera nada."
        )
    )
    parser.add_argument(
        "--exports",
        action="store_true",
        help="imprime as linhas de variavel de ambiente prontas para colar",
    )
    args = parser.parse_args()

    resultados = [checar_rust(), checar_node(), checar_cmake(), checar_libclang()]

    print("Ambiente de build do desktop (npm run tauri dev/build)")
    print("-" * 56)
    for r in resultados:
        marca = "OK    " if r.ok else "FALTA "
        print(f"{marca} {r.nome}: {r.detalhe}")
        for passo in r.como_resolver:
            print(f"         -> {passo}")
    print("-" * 56)

    faltando = [r for r in resultados if not r.ok]
    exports = montar_exports(resultados)

    if args.exports:
        print()
        imprimir_exports(exports)
        print()

    if not faltando:
        print("Tudo pronto. `cargo check` em desktop/src-tauri deve passar.")
        return 0

    print(f"{len(faltando)} item(ns) faltando - `cargo build` do desktop vai falhar.")
    if exports and not args.exports:
        print("Rode com --exports para as linhas de variavel prontas para colar.")
    print("Detalhes e sintomas de cada falha: desktop/README.md, secao")
    print("'Pre-requisitos de build nativo'.")
    print()
    print("Lembrete: `npm test` (vitest) nao depende de nada disso.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
