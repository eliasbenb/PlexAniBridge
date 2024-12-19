from git import InvalidGitRepositoryError, Repo


def get_git_version() -> str:
    try:
        repo = Repo(".", search_parent_directories=True)
        commit_hash = repo.head.commit.hexsha
        is_dirty = repo.is_dirty()
        return f"{commit_hash[:7]}{'-d' if is_dirty else ''}"
    except InvalidGitRepositoryError:
        return "UNKNOWN"
