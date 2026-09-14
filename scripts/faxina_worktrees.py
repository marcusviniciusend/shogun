"""Faxina de worktrees e branches locais mergeadas — dry-run por padrao.

O que e: um script de limpeza do ambiente local de rodadas. O repositorio
acumula worktrees de agentes (C:\\dev\\shogun-wt-*, .claude/worktrees/*) e
branches locais feature/* cujo remoto sumiu depois do merge (upstream
"gone"). Este script lista tudo, classifica com criterios conservadores e —
somente sob flag explicita — remove o que ja esta comprovadamente em
origin/dev.

Quem roda e o humano. Por isso o modo padrao e DRY-RUN: sem flag nenhuma o
script apenas imprime o plano ("removeria X porque Y") e sai com codigo 0,
sem tocar em nada. A execucao real exige --executar E pelo menos uma das
sub-flags de categoria (--worktrees, --branches).

Criterios de seguranca (valem tambem com --executar):

- o checkout principal e o worktree de onde o script roda nunca sao tocados;
- worktree so e candidato se estiver LIMPO (git status --porcelain vazio) e
  com a HEAD ja CONTIDA em origin/dev (git merge-base --is-ancestor); sujo,
  nao contido, locked ou em dev/main aparece como MANTIDO com o motivo;
- worktree cujo diretorio sumiu do disco vira caso de "git worktree prune";
- branch local so e candidata em dois padroes, e nada alem deles:
  * feature/*: exige upstream "gone" E ponta contida em origin/dev — "sem
    upstream" significa trabalho nunca publicado, entao fica;
  * worktree-agent-*: criadas pelo harness do Claude Code para os worktrees
    dos agentes; quando o worktree e removido, a branch fica orfa. Elas nao
    tem upstream POR NATUREZA, entao o criterio "sem upstream = mantida" das
    feature/* NAO se aplica: basta a ponta estar contida em origin/dev;
  a remocao usa git branch -d (minusculo) — o proprio git recusa o que nao
  estiver mergeado. NUNCA -D, nunca push, nunca delecao remota, nunca
  worktree remove --force (o que exigir force fica MANTIDO).

Uso (a partir da raiz do repositorio):

    python scripts/faxina_worktrees.py                          # dry-run
    python scripts/faxina_worktrees.py --no-fetch               # sem git fetch antes
    python scripts/faxina_worktrees.py --executar --worktrees   # remove so worktrees
    python scripts/faxina_worktrees.py --executar --branches    # remove so branches
    python scripts/faxina_worktrees.py --executar --worktrees --branches

Requisitos: Python 3.11+, stdlib apenas. Origem do mandato:
docs/escalabilidade-rodadas.md, secao 4, opcao D.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# categorias de classificacao
PROTEGIDO = "protegido"  # fora de alcance por definicao (principal, worktree atual)
MANTIDO = "mantido"      # examinado e preservado, com motivo
PRUNE = "prune"          # registro de worktree cujo diretorio sumiu do disco
REMOVER = "remover"      # candidato a remocao segura


# ---------------------------------------------------------------------------
# git (I/O)
# ---------------------------------------------------------------------------

def rodar_git(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Roda um comando git e devolve (codigo, stdout, stderr) sem levantar."""
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def git_ou_falha(args: list[str], cwd: Path | None = None) -> str:
    """Roda git e aborta o script com mensagem clara se o comando falhar."""
    codigo, saida, erro = rodar_git(args, cwd)
    if codigo != 0:
        sys.exit(f"erro: git {' '.join(args)} falhou: {erro or saida}")
    return saida


def caminho_normalizado(caminho: str | Path) -> str:
    """Forma canonica de um caminho para comparacao (Windows-friendly)."""
    return os.path.normcase(str(Path(caminho).resolve()))


def worktree_esta_limpo(caminho: Path) -> bool | None:
    """True se git status --porcelain vazio; None se nao deu para verificar."""
    codigo, saida, _ = rodar_git(["-C", str(caminho), "status", "--porcelain"])
    if codigo != 0:
        return None
    return saida == ""


def contido_em(sha: str, base: str) -> bool | None:
    """True se sha ja esta contido em base; None se nao deu para verificar."""
    codigo, _, _ = rodar_git(["merge-base", "--is-ancestor", sha, base])
    if codigo == 0:
        return True
    if codigo == 1:
        return False
    return None


def eh_branch_agente(nome: str) -> bool:
    """True para branches worktree-agent-* (harness do Claude Code).

    Essas branches sao criadas pelo harness para os worktrees dos agentes e
    nunca sao pushadas; quando o worktree e removido, a branch fica orfa.
    Por isso a ASSIMETRIA de criterio em classificar_branch: para elas,
    "sem upstream" e a natureza, nao motivo de manutencao.
    """
    return nome.startswith("worktree-agent-")


# ---------------------------------------------------------------------------
# modelos
# ---------------------------------------------------------------------------

@dataclass
class Worktree:
    caminho: str                 # como o git listou
    head: str = ""
    branch: str | None = None    # nome curto; None quando detached
    locked: bool = False
    prunable: bool = False
    existe: bool = True          # diretorio presente no disco
    limpo: bool | None = None    # None = nao verificado / indeterminado
    contido: bool | None = None  # HEAD contida em origin/dev


@dataclass
class BranchLocal:
    nome: str
    sha: str
    upstream: str                # vazio quando nunca teve upstream
    track: str                   # "[gone]" quando o remoto sumiu
    contido: bool | None = None
    worktree: str | None = None  # caminho do worktree onde esta em uso


# ---------------------------------------------------------------------------
# funcoes puras (classificacao)
# ---------------------------------------------------------------------------

def parse_worktree_porcelain(texto: str) -> list[Worktree]:
    """Interpreta a saida de git worktree list --porcelain."""
    worktrees: list[Worktree] = []
    atual: Worktree | None = None
    for linha in texto.splitlines():
        if linha.startswith("worktree "):
            atual = Worktree(caminho=linha.removeprefix("worktree "))
            worktrees.append(atual)
        elif atual is None:
            continue
        elif linha.startswith("HEAD "):
            atual.head = linha.removeprefix("HEAD ")
        elif linha.startswith("branch "):
            atual.branch = linha.removeprefix("branch ").removeprefix("refs/heads/")
        elif linha == "locked" or linha.startswith("locked "):
            atual.locked = True
        elif linha == "prunable" or linha.startswith("prunable "):
            atual.prunable = True
    return worktrees


def classificar_worktree(
    wt: Worktree, raiz_principal: str, raiz_atual: str
) -> tuple[str, str]:
    """Classifica um worktree ja coletado. Funcao pura: nao roda git.

    raiz_principal e raiz_atual chegam ja normalizados (caminho_normalizado).
    """
    caminho = caminho_normalizado(wt.caminho)
    if caminho == raiz_principal:
        return PROTEGIDO, "checkout principal — nunca tocado"
    if caminho == raiz_atual:
        return PROTEGIDO, "worktree de onde o script esta rodando"
    if wt.prunable or not wt.existe:
        return PRUNE, "diretorio ausente do disco — coberto por git worktree prune"
    if wt.branch in ("dev", "main"):
        return MANTIDO, f"esta em `{wt.branch}` — branch de integracao, fora de alcance"
    if wt.locked:
        return MANTIDO, "locked — remover exigiria force, e force e proibido"
    if wt.limpo is None:
        return MANTIDO, "nao deu para verificar o status — na duvida, fica"
    if wt.limpo is False:
        return MANTIDO, "worktree sujo (git status --porcelain nao vazio)"
    if wt.contido is None:
        return MANTIDO, "nao deu para verificar se a HEAD esta em origin/dev — na duvida, fica"
    if wt.contido is False:
        return MANTIDO, "HEAD nao contida em origin/dev — tem trabalho nao mergeado"
    ref = wt.branch or f"HEAD destacada {wt.head[:7]}"
    return REMOVER, f"limpo e {ref} ja contida em origin/dev"


def classificar_branch(
    br: BranchLocal, worktrees_removiveis: set[str]
) -> tuple[str, str]:
    """Classifica uma branch local. Funcao pura: nao roda git.

    Dois padroes entram na faxina, com criterios ASSIMETRICOS de proposito:

    - feature/*: nasce para ser pushada. "Sem upstream" significa trabalho
      nunca publicado (fica); o criterio exige upstream "gone" + ponta
      contida em origin/dev.
    - worktree-agent-*: criada pelo harness do Claude Code para o worktree
      de um agente, nunca pushada — "sem upstream" e a natureza dela, nao
      um sinal de trabalho nao publicado. O criterio e apenas a ponta
      contida em origin/dev.

    worktrees_removiveis: caminhos normalizados dos worktrees classificados
    como REMOVER — uma branch em uso num deles ainda pode cair, desde que o
    worktree caia antes.
    """
    if br.nome in ("dev", "main"):
        return PROTEGIDO, "branch de integracao — nunca tocada"
    if eh_branch_agente(br.nome):
        # assimetria documentada acima: sem exigencia de upstream/gone.
        if br.upstream and br.track != "[gone]":
            return MANTIDO, (
                f"upstream {br.upstream} ainda existe — fora do padrao das "
                "branches de agente (elas nao tem upstream); na duvida, fica"
            )
    else:
        if not br.upstream:
            return MANTIDO, "sem upstream configurado — nunca foi pushada, nao ha 'gone' para confirmar"
        if br.track != "[gone]":
            return MANTIDO, f"upstream {br.upstream} ainda existe"
    if br.contido is None:
        return MANTIDO, "nao deu para verificar se a ponta esta em origin/dev — na duvida, fica"
    if br.contido is False:
        return MANTIDO, "a ponta NAO esta em origin/dev — tem commit local nao mergeado"
    if br.worktree is not None:
        if caminho_normalizado(br.worktree) in worktrees_removiveis:
            return REMOVER, (
                "mergeada; em uso num worktree que tambem e candidato "
                "(a remocao do worktree precisa vir antes)"
            )
        return MANTIDO, f"em uso no worktree mantido {br.worktree}"
    if eh_branch_agente(br.nome):
        return REMOVER, (
            "mergeada em origin/dev; branch de agente orfa, sem upstream por "
            "natureza (git branch -d confirma)"
        )
    return REMOVER, "mergeada em origin/dev e upstream gone (git branch -d confirma)"


# ---------------------------------------------------------------------------
# coleta (I/O)
# ---------------------------------------------------------------------------

def coletar_worktrees(base: str) -> list[Worktree]:
    saida = git_ou_falha(["worktree", "list", "--porcelain"])
    worktrees = parse_worktree_porcelain(saida)
    for wt in worktrees:
        wt.existe = Path(wt.caminho).is_dir()
        if wt.existe and not wt.prunable:
            wt.limpo = worktree_esta_limpo(Path(wt.caminho))
            wt.contido = contido_em(wt.head, base) if wt.head else None
    return worktrees


def coletar_branches(base: str, worktrees: list[Worktree]) -> list[BranchLocal]:
    # os dois unicos padroes no escopo da faxina — e nada alem deles.
    saida = git_ou_falha([
        "for-each-ref", "refs/heads/feature/*", "refs/heads/worktree-agent-*",
        "--format=%(refname:short)|%(objectname)|%(upstream:short)|%(upstream:track)",
    ])
    em_uso = {
        wt.branch: wt.caminho for wt in worktrees if wt.branch and wt.existe
    }
    branches: list[BranchLocal] = []
    for linha in saida.splitlines():
        if not linha.strip():
            continue
        nome, sha, upstream, track = (linha.split("|") + ["", "", ""])[:4]
        br = BranchLocal(nome=nome, sha=sha, upstream=upstream, track=track)
        if eh_branch_agente(nome):
            # branch de agente: sem upstream por natureza — verifica a ponta
            # sempre que o criterio de upstream nao a mantiver antes.
            if not upstream or track == "[gone]":
                br.contido = contido_em(sha, base)
        elif upstream and track == "[gone]":
            br.contido = contido_em(sha, base)
        br.worktree = em_uso.get(nome)
        branches.append(br)
    return branches


# ---------------------------------------------------------------------------
# relatorio e execucao
# ---------------------------------------------------------------------------

def rotulo(categoria: str, executando: bool) -> str:
    if categoria == REMOVER:
        return "REMOVER" if executando else "REMOVERIA"
    if categoria == PRUNE:
        return "PRUNE" if executando else "PRUNARIA"
    return categoria.upper()


def imprimir_plano(
    worktrees: list[tuple[Worktree, str, str]],
    branches: list[tuple[BranchLocal, str, str]],
    executando_worktrees: bool,
    executando_branches: bool,
) -> None:
    """Imprime o plano. Os flags de execucao sao POR CATEGORIA: com
    `--executar --branches` (sem --worktrees), os worktrees continuam no
    condicional ("REMOVERIA") — nada fora da categoria pedida vira "REMOVER".
    """
    print("== Worktrees ==")
    for wt, categoria, motivo in worktrees:
        alvo = wt.caminho + (f" [{wt.branch}]" if wt.branch else " [detached]")
        print(f"  {rotulo(categoria, executando_worktrees)}: {alvo} — {motivo}")
    print()
    print("== Branches locais (feature/*, worktree-agent-*) ==")
    if not branches:
        print("  (nenhuma branch feature/* ou worktree-agent-* local)")
    for br, categoria, motivo in branches:
        print(f"  {rotulo(categoria, executando_branches)}: {br.nome} — {motivo}")
    print()


def executar_worktrees(
    classificados: list[tuple[Worktree, str, str]]
) -> tuple[int, int]:
    """Remove os worktrees candidatos e roda prune. Devolve (ok, falhas)."""
    ok = falhas = 0
    for wt, categoria, _ in classificados:
        if categoria != REMOVER:
            continue
        codigo, saida, erro = rodar_git(["worktree", "remove", wt.caminho])
        if codigo == 0:
            print(f"removido worktree: {wt.caminho}")
            ok += 1
        else:
            # git recusou (ex.: sujou entre a coleta e agora). Sem --force, nunca.
            print(f"MANTIDO (git recusou): {wt.caminho} — {erro or saida}")
            falhas += 1
    if any(categoria == PRUNE for _, categoria, _ in classificados):
        codigo, saida, erro = rodar_git(["worktree", "prune", "--verbose"])
        if codigo == 0:
            for linha in (saida or erro).splitlines():
                print(f"prune: {linha.strip()}")
            print("git worktree prune executado")
        else:
            print(f"AVISO: git worktree prune falhou — {erro or saida}")
            falhas += 1
    return ok, falhas


def executar_branches(
    classificados: list[tuple[BranchLocal, str, str]]
) -> tuple[int, int]:
    """Remove as branches candidatas com git branch -d. Devolve (ok, falhas)."""
    ok = falhas = 0
    for br, categoria, _ in classificados:
        if categoria != REMOVER:
            continue
        # -d minusculo E a rede de seguranca: o git recusa o nao mergeado.
        codigo, saida, erro = rodar_git(["branch", "-d", br.nome])
        if codigo == 0:
            print(f"removida branch: {br.nome} (era {br.sha[:7]})")
            ok += 1
        else:
            print(f"MANTIDA (git recusou): {br.nome} — {erro or saida}")
            falhas += 1
    return ok, falhas


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Faxina de worktrees e branches locais ja mergeadas. Sem flags: "
            "dry-run — imprime o plano e nao toca em nada."
        )
    )
    parser.add_argument(
        "--executar", action="store_true",
        help="executa de verdade (exige tambem --worktrees e/ou --branches)",
    )
    parser.add_argument(
        "--worktrees", action="store_true",
        help="com --executar: remove os worktrees candidatos e roda prune",
    )
    parser.add_argument(
        "--branches", action="store_true",
        help="com --executar: remove as branches candidatas com git branch -d",
    )
    parser.add_argument(
        "--no-fetch", action="store_true",
        help="nao rodar git fetch --prune antes (o 'gone' pode estar defasado)",
    )
    args = parser.parse_args()

    if args.executar and not (args.worktrees or args.branches):
        parser.error(
            "--executar exige escolher a categoria: --worktrees, --branches ou ambas"
        )
    if (args.worktrees or args.branches) and not args.executar:
        parser.error(
            "--worktrees/--branches so fazem sentido com --executar; "
            "o dry-run (padrao) ja cobre as duas categorias"
        )

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass  # stdout nao reconfiguravel (ex.: redirecionado); segue como esta

    git_ou_falha(["rev-parse", "--git-dir"])  # falha cedo fora de um repo
    comum = git_ou_falha(["rev-parse", "--path-format=absolute", "--git-common-dir"])
    raiz_principal = caminho_normalizado(Path(comum).parent)
    raiz_atual = caminho_normalizado(git_ou_falha(["rev-parse", "--show-toplevel"]))

    if not args.no_fetch:
        codigo, _, erro = rodar_git(["fetch", "--prune", "origin"])
        if codigo != 0:
            print(
                f"aviso: git fetch falhou ({erro}); seguindo com o estado local "
                "(o 'gone' e a posicao de origin/dev podem estar defasados)",
                file=sys.stderr,
            )

    base = "origin/dev"
    git_ou_falha(["rev-parse", "--verify", base])  # sem origin/dev nao ha criterio

    worktrees = coletar_worktrees(base)
    wt_classificados = [
        (wt, *classificar_worktree(wt, raiz_principal, raiz_atual))
        for wt in worktrees
    ]
    removiveis = {
        caminho_normalizado(wt.caminho)
        for wt, categoria, _ in wt_classificados
        if categoria == REMOVER
    }
    branches = coletar_branches(base, worktrees)
    br_classificados = [
        (br, *classificar_branch(br, removiveis)) for br in branches
    ]

    try:
        if not args.executar:
            print("Modo DRY-RUN (padrao): nada sera tocado. Plano:\n")
            imprimir_plano(
                wt_classificados, br_classificados,
                executando_worktrees=False, executando_branches=False,
            )
            n_wt = sum(1 for _, c, _ in wt_classificados if c == REMOVER)
            n_pr = sum(1 for _, c, _ in wt_classificados if c == PRUNE)
            n_br = sum(1 for _, c, _ in br_classificados if c == REMOVER)
            print(
                f"Resumo do plano: {n_wt} worktree(s) removiveis, {n_pr} para prune, "
                f"{n_br} branch(es) removiveis."
            )
            print(
                "Para executar: --executar com --worktrees e/ou --branches. "
                "Worktrees primeiro, se for rodar as duas em separado."
            )
            return

        if args.branches and not args.worktrees:
            # sem --worktrees nesta execucao, o worktree candidato NAO vai
            # cair antes — o git recusaria deletar a branch em uso nele.
            # Rebaixa para MANTIDA com o motivo certo em vez de colecionar
            # uma recusa previsivel (e um exit 1) do git.
            br_classificados = [
                (br, MANTIDO,
                 "em uso num worktree candidato ainda presente — rode com "
                 "--worktrees (antes ou junto) para o worktree cair primeiro")
                if categoria == REMOVER and br.worktree is not None
                else (br, categoria, motivo)
                for br, categoria, motivo in br_classificados
            ]

        print("Modo EXECUCAO. Plano aprovado pelas flags:\n")
        # com --worktrees --branches juntos, a ordem interna abaixo ja
        # garante "worktrees primeiro" — a dependencia so exige atencao do
        # humano quando as categorias rodam em execucoes separadas.
        imprimir_plano(
            wt_classificados, br_classificados,
            executando_worktrees=args.worktrees,
            executando_branches=args.branches,
        )

        ok_wt = falhas_wt = ok_br = falhas_br = 0
        if args.worktrees:
            ok_wt, falhas_wt = executar_worktrees(wt_classificados)
        if args.branches:
            ok_br, falhas_br = executar_branches(br_classificados)

        mantidos_wt = sum(1 for _, c, _ in wt_classificados if c == MANTIDO)
        mantidas_br = sum(1 for _, c, _ in br_classificados if c == MANTIDO)
        partes = []
        if args.worktrees:
            partes.append(
                f"{ok_wt} worktree(s) removidos, {mantidos_wt} mantido(s) por criterio"
            )
        else:
            partes.append("worktrees fora desta execucao (sem --worktrees)")
        if args.branches:
            partes.append(
                f"{ok_br} branch(es) removidas, {mantidas_br} mantida(s) por criterio"
            )
        else:
            partes.append("branches fora desta execucao (sem --branches)")
        print()
        print(
            f"Resumo: {'; '.join(partes)}; {falhas_wt + falhas_br} recusa(s) do git."
        )
        if falhas_wt + falhas_br:
            sys.exit(1)
    except (BrokenPipeError, OSError):
        # leitor fechou o pipe cedo (ex.: | head); nao e erro do script
        sys.exit(0)


if __name__ == "__main__":
    main()
