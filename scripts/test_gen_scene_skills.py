from gen_scene_skills import plan_changes, scene_dir_name


def test_scene_dir_name_uses_skill_frontmatter_slug():
    md = '---\nname: cue-credit-diligence\nscene: "信贷尽调"\n---\n# x'
    assert scene_dir_name(md) == "cue-credit-diligence"


def test_plan_changes_add_update_delete():
    # existing on disk: {a, b}; live scenes now: {b, c} → write {b,c}, delete a
    existing = {"cue-a", "cue-b"}
    live = {"cue-b", "cue-c"}
    add, delete = plan_changes(live, existing)
    assert add == {"cue-b", "cue-c"} and delete == {"cue-a"}
