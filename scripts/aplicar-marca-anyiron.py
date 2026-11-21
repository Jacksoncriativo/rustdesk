#!/usr/bin/env python3
"""
Aplica o branding Anyiron (nome, servidor, chave publica e icones opcionais)
em um clone do repositorio rustdesk/rustdesk (com submodulos inicializados).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path


def escape_c_rust(value: str) -> str:
    """Valida e escapa string para literais em Rust e arquivos .rc."""
    if "\n" in value or "\r" in value:
        raise ValueError("Valores nao podem conter quebras de linha.")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def replace_required(
    content: str,
    pattern: str,
    replacement_fn,
    label: str,
    file_path: Path,
) -> str:
    """Executa substituicao regex exigindo pelo menos 1 ocorrencia."""
    new_content, count = re.subn(pattern, replacement_fn, content, count=1)
    if count == 0:
        raise RuntimeError(
            f"Padrao esperado '{label}' nao encontrado em '{file_path}'."
        )
    return new_content


def patch_config_rs(
    repo: Path,
    app_name: str,
    server: str,
    pub_key: str,
    dry_run: bool,
) -> list[str]:
    """Atualiza APP_NAME, RENDEZVOUS_SERVERS e RS_PUB_KEY em hbb_common/src/config.rs."""
    config_path = repo / "libs" / "hbb_common" / "src" / "config.rs"
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Arquivo '{config_path}' nao encontrado. "
            "Certifique-se de clonar o repositorio com submodulos (--recursive)."
        )

    content = config_path.read_text(encoding="utf-8")
    changes: list[str] = []

    safe_name = escape_c_rust(app_name)
    content = replace_required(
        content,
        r'(pub\s+static\s+ref\s+APP_NAME:\s*RwLock<String>\s*=\s*RwLock::new\()"([^"]*)"(\.to_owned\(\)\);)',
        lambda m: f'{m.group(1)}"{safe_name}"{m.group(3)}',
        "APP_NAME",
        config_path,
    )
    changes.append(f'APP_NAME -> "{app_name}"')

    if server:
        safe_server = escape_c_rust(server)
        content = replace_required(
            content,
            r"(pub\s+const\s+RENDEZVOUS_SERVERS:\s*&\[&str\]\s*=\s*&\[)[^\]]*(\];)",
            lambda m: f'{m.group(1)}"{safe_server}"{m.group(2)}',
            "RENDEZVOUS_SERVERS",
            config_path,
        )
        changes.append(f'RENDEZVOUS_SERVERS -> &["{server}"]')

    if pub_key:
        safe_key = escape_c_rust(pub_key)
        content = replace_required(
            content,
            r'(pub\s+const\s+RS_PUB_KEY:\s*&str\s*=\s*)"([^"]*)";',
            lambda m: f'{m.group(1)}"{safe_key}";',
            "RS_PUB_KEY",
            config_path,
        )
        changes.append('RS_PUB_KEY -> "<chave configurada>"')

    if not dry_run:
        config_path.write_text(content, encoding="utf-8")

    return changes


def patch_runner_rc(
    repo: Path,
    app_name: str,
    dry_run: bool,
) -> list[str]:
    """Atualiza metadados do executavel Windows em flutter/windows/runner/Runner.rc."""
    rc_path = repo / "flutter" / "windows" / "runner" / "Runner.rc"
    if not rc_path.is_file():
        raise FileNotFoundError(f"Arquivo '{rc_path}' nao encontrado.")

    content = rc_path.read_text(encoding="utf-8")
    safe_name = escape_c_rust(app_name)
    safe_internal = escape_c_rust(re.sub(r"[^a-z0-9_-]+", "", app_name.lower()) or "anyiron")

    replacements = [
        ("FileDescription", f"{safe_name} Remote Desktop"),
        ("InternalName", safe_internal),
        ("OriginalFilename", f"{safe_name}.exe"),
        ("ProductName", safe_name),
    ]

    changes: list[str] = []
    for field, value in replacements:
        pattern = rf'(VALUE\s+"{field}",\s*)"[^"]*"'
        content = replace_required(
            content,
            pattern,
            lambda m, v=value: f'{m.group(1)}"{v}"',
            field,
            rc_path,
        )
        changes.append(f'{field} -> "{value}"')

    if not dry_run:
        rc_path.write_text(content, encoding="utf-8")

    return changes


def copy_icons(
    repo: Path,
    icon_ico: str | None,
    icon_png: str | None,
    dry_run: bool,
) -> list[str]:
    """Copia icones personalizados (.ico / .png) para os caminhos esperados."""
    actions: list[str] = []

    if icon_ico:
        src_ico = Path(icon_ico)
        if not src_ico.is_file():
            raise FileNotFoundError(f"Icone .ico nao encontrado: '{src_ico}'")

        targets = [
            repo / "flutter" / "windows" / "runner" / "resources" / "app_icon.ico",
        ]
        for extra in (repo / "res" / "icon.ico", repo / "res" / "tray-icon.ico"):
            if extra.parent.is_dir():
                targets.append(extra)

        for dst in targets:
            if not dst.parent.is_dir():
                raise FileNotFoundError(
                    f"Diretorio de destino do icone nao encontrado: '{dst.parent}'"
                )
            if not dry_run:
                shutil.copy2(src_ico, dst)
            actions.append(f"{src_ico} -> {dst.relative_to(repo)}")

    if icon_png:
        src_png = Path(icon_png)
        if not src_png.is_file():
            raise FileNotFoundError(f"Icone .png nao encontrado: '{src_png}'")

        candidate_dirs = [repo / "res", repo / "assets"]
        matched_targets = [d / "icon.png" for d in candidate_dirs if d.is_dir()]
        if not matched_targets:
            raise FileNotFoundError(
                "Nenhum diretorio 'res/' ou 'assets/' encontrado para copiar icon.png."
            )

        for dst in matched_targets:
            if not dry_run:
                shutil.copy2(src_png, dst)
            actions.append(f"{src_png} -> {dst.relative_to(repo)}")

    return actions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aplica o branding Anyiron no codigo-fonte do RustDesk."
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Caminho para o repositorio rustdesk clonado localmente.",
    )
    parser.add_argument(
        "--name",
        default="Anyiron",
        help="Nome do aplicativo (padrao: Anyiron).",
    )
    parser.add_argument(
        "--server",
        default=os.environ.get("ANYIRON_SERVER", ""),
        help="IP ou dominio do servidor hbbs (ou env ANYIRON_SERVER).",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("ANYIRON_KEY", ""),
        help="Chave publica id_ed25519.pub (ou env ANYIRON_KEY).",
    )
    parser.add_argument(
        "--icon-ico",
        default=None,
        help="Caminho opcional para um arquivo .ico personalizado.",
    )
    parser.add_argument(
        "--icon-png",
        default=None,
        help="Caminho opcional para um arquivo .png personalizado.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula as alteracoes sem gravar arquivos.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"Erro: diretorio do repositorio nao existe: '{repo}'", file=sys.stderr)
        return 1

    app_name = args.name.strip()
    if not app_name:
        print("Erro: --name nao pode ser vazio.", file=sys.stderr)
        return 1

    server = args.server.strip()
    pub_key = args.key.strip()

    try:
        cfg_changes = patch_config_rs(repo, app_name, server, pub_key, args.dry_run)
        rc_changes = patch_runner_rc(repo, app_name, args.dry_run)
        icon_changes = copy_icons(repo, args.icon_ico, args.icon_png, args.dry_run)
    except Exception as exc:
        print(f"Erro ao aplicar marca '{app_name}': {exc}", file=sys.stderr)
        return 1

    mode = "[DRY-RUN] " if args.dry_run else ""
    print(f"{mode}Branding '{app_name}' aplicado com sucesso em '{repo}':")
    for item in cfg_changes:
        print(f"  - config.rs: {item}")
    for item in rc_changes:
        print(f"  - Runner.rc: {item}")
    for item in icon_changes:
        print(f"  - icone: {item}")

    if not server or not pub_key:
        print(
            "Aviso: --server ou --key nao foram informados; "
            "valores padrao de servidor/chave nao alterados."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
