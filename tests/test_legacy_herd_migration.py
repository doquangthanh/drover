from drover.legacy_herd_migration import move_legacy_dir


def test_moves_old_herd_folder_to_drover(tmp_path):
    old = tmp_path / "herd"
    (old / "rules").mkdir(parents=True)
    (old / "settings.toml").write_text("theme = 'dark'\n", encoding="utf-8")
    move_legacy_dir(tmp_path / "drover")
    assert (tmp_path / "drover" / "settings.toml").read_text(encoding="utf-8") == "theme = 'dark'\n"
    assert (tmp_path / "drover" / "rules").is_dir()
    assert not old.exists()


def test_leaves_existing_drover_folder_alone(tmp_path):
    (tmp_path / "herd").mkdir()
    (tmp_path / "herd" / "settings.toml").write_text("old", encoding="utf-8")
    (tmp_path / "drover").mkdir()
    move_legacy_dir(tmp_path / "drover")
    assert not (tmp_path / "drover" / "settings.toml").exists()
    assert (tmp_path / "herd").exists()


def test_no_old_folder_is_a_no_op(tmp_path):
    move_legacy_dir(tmp_path / "drover")
    assert not (tmp_path / "drover").exists()


def test_ignores_folders_with_other_names(tmp_path):
    (tmp_path / "herd").mkdir()
    move_legacy_dir(tmp_path / "custom-state")
    assert (tmp_path / "herd").exists()
