from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from git import Repo, InvalidGitRepositoryError


@dataclass(frozen=True)
class CommitChange:
    """Files changed by one Git commit."""

    commit_hash: str
    timestamp: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class CoChange:
    """Historical frequency of two files changing together."""

    file_a: str
    file_b: str
    frequency: int


class GitHistoryMiner:
    """
    Mines Git history to discover files that frequently change together.
    """

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()

        try:
            self.repo = Repo(self.repo_path)
        except InvalidGitRepositoryError as exc:
            raise ValueError(
                f"Not a Git repository: {self.repo_path}"
            ) from exc

    def mine_commits(
        self,
        max_commits: int | None = None,
    ) -> tuple[CommitChange, ...]:
        """
        Extract changed files from Git commits.

        Each commit contains each changed file at most once.
        """

        commits = []

        commit_iter = self.repo.iter_commits()

        if max_commits is not None:
            commit_iter = list(commit_iter)[:max_commits]

        for commit in commit_iter:
            files = self._changed_files(commit)

            if not files:
                continue

            commits.append(
                CommitChange(
                    commit_hash=commit.hexsha,
                    timestamp=commit.committed_datetime.isoformat(),
                    files=tuple(sorted(files)),
                )
            )

        return tuple(commits)

    def build_cochange_matrix(
        self,
        max_commits: int | None = None,
    ) -> tuple[CoChange, ...]:
        """
        Count how many commits changed each pair of files together.
        """

        commits = self.mine_commits(
            max_commits=max_commits
        )

        frequencies: Counter[tuple[str, str]] = Counter()

        for commit in commits:
            # combinations() creates every unique pair once.
            for file_a, file_b in combinations(
                commit.files,
                2,
            ):
                pair = tuple(
                    sorted((file_a, file_b))
                )

                frequencies[pair] += 1

        return tuple(
            CoChange(
                file_a=file_a,
                file_b=file_b,
                frequency=frequency,
            )
            for (file_a, file_b), frequency
            in sorted(
                frequencies.items(),
                key=lambda item: (
                    -item[1],
                    item[0][0],
                    item[0][1],
                ),
            )
        )

    def cochange_for_file(
        self,
        file_path: str,
        max_commits: int | None = None,
    ) -> tuple[CoChange, ...]:
        """
        Return all historical co-change relationships
        involving a specific file.
        """

        relationships = self.build_cochange_matrix(
            max_commits=max_commits
        )

        return tuple(
            relationship
            for relationship in relationships
            if (
                relationship.file_a == file_path
                or relationship.file_b == file_path
            )
        )

    def _changed_files(self, commit) -> set[str]:
        """
        Return project-relative paths changed by a commit.
        """

        files: set[str] = set()

        if commit.parents:
            parent = commit.parents[0]

            diffs = parent.diff(
                commit,
                paths=None,
                create_patch=False,
            )

            for diff in diffs:
                if diff.a_path:
                    files.add(diff.a_path)

                if diff.b_path:
                    files.add(diff.b_path)

        else:
            # Handle the initial commit separately.
            for item in commit.tree.traverse():
                if item.type == "blob":
                    files.add(item.path)

        return files