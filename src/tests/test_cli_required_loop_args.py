from agentforge.cli_args import build_parser


def test_cli_run_accepts_llama_launcher_flags():
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--server-exe",
            "llama-server.exe",
            "--models-dir",
            "models",
        ]
    )
    assert args.command == "run"
    assert args.server_exe == "llama-server.exe"
    assert args.models_dir == "models"
