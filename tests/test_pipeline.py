"""Tests for the log pipeline. Run with:  python -m unittest   (or pytest)."""
import os
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp()
os.environ["POETRACKER_HOME"] = TMP

from poetracker import captures, config, db, ingest, metrics  # noqa: E402

PID = 4242


def L(t, msg, lvl="INFO"):
    return f"2026/07/28 {t} 1 abc [{lvl} Client {PID}] {msg}\r\n"


def gen(t, area, level, seed):
    return L(t, f'Generating level {level} area "{area}" with seed {seed}', "DEBUG")


LOG = (
    "2026/07/28 16:00:00 ***** LOG FILE OPENING *****\r\n"
    + L("16:00:05", "Async connecting to dal.login.pathofexile.com:20483")
    + gen("16:01:00", "1_1_1", 1, 111) + L("16:01:01", ": You have entered The Twilight Strand.")
    + L("16:03:00", ": Hero (Marauder) is now level 2")
    + gen("16:05:00", "1_1_town", 13, 1) + L("16:05:01", ": You have entered Lioneye's Watch.")
    + gen("16:10:00", "1_2_1", 13, 222) + L("16:10:01", ": You have entered The Southern Forest.")
    + L("16:12:00", ": Hero has been slain.")
    + L("16:13:00", ": Buddy has joined the area.")
    + L("16:13:30", ": Buddy (Witch) is now level 40")
    + gen("16:20:00", "2_11_endgame_town", 68, 1) + L("16:20:01", ": You have entered Karui Shores.")
    # map with a portal back and a side area
    + gen("16:30:00", "HideoutTemplarLab", 60, 1)
    + gen("16:31:00", "MapWorldsJungleValley", 83, 999) + L("16:31:01", ": You have entered Jungle Valley.")
    + L("16:32:00", "Einhar, Beastmaster: Ha! Yes!")
    + gen("16:35:00", "HideoutTemplarLab", 60, 1)
    + gen("16:36:00", "MapWorldsJungleValley", 83, 999)
    + gen("16:38:00", "MapSideArea5_2", 83, 555)
    + gen("16:40:00", "MapWorldsJungleValley", 83, 999)
    + L("16:41:00", "Successfully allocated passive skill id: atlas_breach_1, name: Breach Chance")
    + gen("16:45:00", "HideoutTemplarLab", 60, 1)
    + gen("16:46:00", "MapWorldsCitySquare", 80, 1234) + L("16:46:01", ": You have entered City Square.")
    + L("16:47:00", ": AFK mode is now ON. Autoreply \"This player is AFK.\"")
    + L("16:57:00", ": AFK mode is now OFF.")
    + gen("16:58:00", "HideoutTemplarLab", 60, 1)
    + L("16:59:00", "@From <GLD> Trader: Hi, I would like to buy your Tabula Rasa listed for 10 chaos in Curse of the Allflame (stash tab \"x\"; position: left 1, top 2)")
    + L("17:00:00", "Closing game gracefully")
)

MAP_TEXT = """Item Class: Maps
Rarity: Rare
Doom Spires
City Square Map
--------
Map Tier: 13
Item Quantity: +72% (augmented)
Item Rarity: +40% (augmented)
Monster Pack Size: +25% (augmented)
More Scarabs: +20% (augmented)
--------
Item Level: 80
--------
Monster Level: 80
--------
Monsters deal 90% extra Physical Damage as Fire
Players are Cursed with Elemental Weakness
--------
Travel to this Map by using it in a personal Map Device. Maps can only be used once.
--------
Corrupted
"""


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = Path(TMP) / "Client.txt"
        cls.log.write_bytes(LOG.encode())
        cls.cfg = config.load_config()
        cls.con = db.open_db(Path(TMP) / "t.db")
        # Copy the map 5 seconds before the City Square run starts (UTC = local+5h in July)
        cls.con.execute("DELETE FROM map_capture")
        from datetime import datetime, timezone
        captures.save_capture(cls.con, MAP_TEXT, datetime(2026, 7, 28, 21, 45, 55, tzinfo=timezone.utc))
        cls.ing = ingest.Ingestor(cls.con, cls.cfg, cls.log)
        cls.events = cls.ing.run_once()
        captures.link_pending(cls.con, cls.cfg)

    def q(self, sql, *a):
        return self.con.execute(sql, a).fetchall()

    def test_character_identified_and_party_member_ignored(self):
        own = [r["name"] for r in self.q("SELECT name FROM v_own_character")]
        self.assertEqual(own, ["Hero"])
        self.assertEqual(self.q("SELECT other FROM character WHERE name='Buddy'")[0][0], 1)
        # the Twilight Strand visit (before the level-up line) got re-attributed
        self.assertEqual(self.q("SELECT c.name FROM area_visit v JOIN character c ON c.id=v.character_id WHERE area_id='1_1_1'")[0][0], "Hero")

    def test_map_runs(self):
        runs = self.q("SELECT area_name, tier, seed FROM run WHERE kind='map' ORDER BY start_utc")
        self.assertEqual([(r[0], r[1]) for r in runs], [("Jungle Valley", 16), ("City Square", 13)])
        jv = self.q("SELECT id FROM run WHERE seed=999")[0][0]
        # 3 entries into the map + 1 side area, all in one run
        self.assertEqual(self.q("SELECT COUNT(*) FROM area_visit WHERE run_id=?", jv)[0][0], 4)
        r = metrics.runs(self.con, self.cfg, None, None)
        jvr = next(x for x in r if x["id"] == jv)
        self.assertIn("Bestiary", jvr["mechanics"])
        self.assertIn("Vaal side area", jvr["mechanics"])
        # 4m + 2m + 2m + 5m inside, hideout time excluded
        self.assertEqual(jvr["active_s"], 13 * 60)

    def test_afk_excluded(self):
        cs = next(x for x in metrics.runs(self.con, self.cfg, None, None) if x["area_name"] == "City Square")
        self.assertEqual(cs["active_s"], 2 * 60)  # 12 min visit - 10 min AFK

    def test_campaign(self):
        cid = self.q("SELECT id FROM character WHERE name='Hero'")[0][0]
        cp = metrics.campaign_for(self.con, cid)
        self.assertEqual([a["act"] for a in cp["acts"]], [1, 2])
        self.assertEqual(cp["deaths"], 1)
        self.assertFalse(cp["completed"])  # reached Karui Shores without act 10

    def test_capture_parsed_and_linked(self):
        p = captures.parse_map_text(MAP_TEXT)
        self.assertEqual((p["tier"], p["quantity"], p["pack_size"], p["corrupted"]), (13, 72, 25, True))
        self.assertEqual(p["properties"]["More Scarabs"], 20)
        self.assertEqual(len(p["mods"]), 2)
        linked = self.q("SELECT r.area_name FROM map_capture m JOIN run r ON r.id=m.run_id")
        self.assertEqual(linked[0][0], "City Square")

    def test_trade_and_atlas(self):
        w = self.q("SELECT item, price_amount, price_currency, who FROM whisper")[0]
        self.assertEqual(tuple(w), ("Tabula Rasa", 10.0, "Chaos Orb", "Trader"))
        st = metrics.passive_state(self.con, league="Curse of the Allflame", tree="atlas")
        self.assertEqual(st["count"], 1)

    def test_incremental_is_idempotent(self):
        before = self.q("SELECT COUNT(*) FROM area_visit")[0][0]
        self.assertEqual(self.ing.run_once(), 0)
        n = ingest.rebuild(self.con, self.cfg, self.log)
        self.assertEqual(n, self.events)
        self.assertEqual(self.q("SELECT COUNT(*) FROM area_visit")[0][0], before)

    def test_log_reset_new_generation(self):
        con = db.open_db(Path(TMP) / "t2.db")
        log = Path(TMP) / "Client2.txt"
        log.write_bytes(LOG.encode())
        ing = ingest.Ingestor(con, self.cfg, log)
        ing.run_once()
        log.write_bytes(LOG.encode()[:400])  # smaller file: game recreated the log
        ing.run_once()
        self.assertEqual(db.get_state(con, "log_generation"), 2)
        self.assertTrue(self.q("SELECT 1"))


if __name__ == "__main__":
    unittest.main()
