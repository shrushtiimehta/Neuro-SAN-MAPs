"""Every config seed must carry the Learned rules header.

PromoteTrial._mirror_to_seed is append-only: it never creates the section, so a
seed missing the header silently returns 'section_missing' and every confirmed
rule is lost on the next from-scratch run (SeedPlaybooks overwrite=True).
"""

from pathlib import Path

from coded_tools.promote_trial import PromoteTrial


def test_every_seed_has_learned_section():
    # The trailing newline matters — _mirror_to_seed matches header + "\n".
    anchor = PromoteTrial.LEARNED_SECTION + "\n"
    for domain, fname in PromoteTrial.SEED_FILES.items():
        seed = Path(PromoteTrial.SEED_DIR) / fname
        assert seed.exists(), f"{domain}: seed missing at {seed}"
        assert anchor in seed.read_text(encoding="utf-8"), f"{domain}: {fname} has no {anchor!r}"


if __name__ == "__main__":
    test_every_seed_has_learned_section()
    print("ok")
