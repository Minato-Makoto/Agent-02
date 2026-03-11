from agentforge.cli_args import build_parser


def test_cli_run_alias_accepts_gateway_flags_and_legacy_positionals():
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "dummy.gguf",
            "--provider",
            "local",
            "--server-exe",
            "llama-server.exe",
            "--open-browser",
        ]
    )
    assert args.command == "run"
    assert args.model == "dummy.gguf"
    assert args.provider == "local"
    assert args.server_exe == "llama-server.exe"
    assert args.open_browser is True
