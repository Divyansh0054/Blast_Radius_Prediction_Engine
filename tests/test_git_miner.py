from pathlib import Path
from git import Repo

from core.git_miner import GitHistoryMiner


def create_repo(tmp_path):
    repo = Repo.init(tmp_path)

    return repo


def commit_files(repo, files, message):
    for path, content in files.items():
        file_path = Path(repo.working_tree_dir) / path
        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        file_path.write_text(
            content,
            encoding="utf-8",
        )

    repo.index.add(list(files.keys()))
    repo.index.commit(message)


def test_mine_commits_returns_changed_files(tmp_path):
    repo = create_repo(tmp_path)

    commit_files(
        repo,
        {
            "main.py": "print('hello')",
            "utils.py": "def add(): pass",
        },
        "initial commit",
    )

    miner = GitHistoryMiner(tmp_path)

    commits = miner.mine_commits()

    assert len(commits) == 1

    assert set(commits[0].files) == {
        "main.py",
        "utils.py",
    }


def test_cochange_frequency(tmp_path):
    repo = create_repo(tmp_path)

    commit_files(
        repo,
        {
            "main.py": "print('hello')",
            "utils.py": "def add(): pass",
        },
        "initial commit",
    )

    commit_files(
        repo,
        {
            "main.py": "print('hello world')",
            "utils.py": "def add(a, b): return a + b",
        },
        "second commit",
    )

    miner = GitHistoryMiner(tmp_path)

    relationships = miner.build_cochange_matrix()

    relationship = next(
        item
        for item in relationships
        if {
            item.file_a,
            item.file_b,
        }
        == {
            "main.py",
            "utils.py",
        }
    )

    assert relationship.frequency == 2


def test_different_files_do_not_create_self_pair(tmp_path):
    repo = create_repo(tmp_path)

    commit_files(
        repo,
        {
            "main.py": "print('hello')",
            "utils.py": "def add(): pass",
            "config.py": "DEBUG = True",
        },
        "initial commit",
    )

    miner = GitHistoryMiner(tmp_path)

    relationships = miner.build_cochange_matrix()

    for relationship in relationships:
        assert relationship.file_a != relationship.file_b


def test_cochange_for_file(tmp_path):
    repo = create_repo(tmp_path)

    commit_files(
        repo,
        {
            "main.py": "print('hello')",
            "utils.py": "def add(): pass",
        },
        "initial commit",
    )

    commit_files(
        repo,
        {
            "main.py": "print('updated')",
        },
        "second commit",
    )

    miner = GitHistoryMiner(tmp_path)

    relationships = miner.cochange_for_file(
        "main.py"
    )

    assert len(relationships) == 1

    assert relationships[0].frequency == 1


def test_max_commits_limits_history(tmp_path):
    repo = create_repo(tmp_path)

    commit_files(
        repo,
        {
            "main.py": "1",
            "utils.py": "1",
        },
        "initial commit",
    )

    commit_files(
        repo,
        {
            "main.py": "2",
            "utils.py": "2",
        },
        "second commit",
    )

    miner = GitHistoryMiner(tmp_path)

    commits = miner.mine_commits(
        max_commits=1
    )

    assert len(commits) == 1