import unittest
import os
import tempfile
import io

from oplus import simulate, Epm
from tests.util import iter_eplus_versions
from oplus.compatibility import get_eplus_base_dir_path


class SimulateTest(unittest.TestCase):
    """
    we test everything in one simulation, for performance reasons
    """
    def test_simulate(self):
        for eplus_version in iter_eplus_versions(self):
            # prepare paths
            idf_path = os.path.join(
                get_eplus_base_dir_path(eplus_version),
                "ExampleFiles",
                "1ZoneEvapCooler.idf"
            )
            epw_path = os.path.join(
                get_eplus_base_dir_path(eplus_version),
                "WeatherData",
                "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
            )

            # prepare a quick simulation
            idf = Epm.load(idf_path)
            sc = idf.SimulationControl.one()
            sc.run_simulation_for_sizing_periods = "No"
            rp = idf.RunPeriod.one()
            rp.end_month = 1
            rp.end_day_of_month = 1

            # prepare outputs
            out_f = io.StringIO()
            err_f = io.StringIO()

            # simulate
            with tempfile.TemporaryDirectory() as dir_path:

                s = simulate(
                    idf,
                    epw_path,
                    dir_path,
                    stdout=out_f,
                    stderr=err_f,
                    beat_freq=0.1
                )

                # check one day output
                eso_df = s.get_out_eso().get_data()
                self.assertEqual(24, len(eso_df))

            # check err (manage differences between eplus versions)
            err_out = err_f.getvalue()
            self.assertTrue(
                (err_out == "") or
                ("EnergyPlus Completed Successfully.\n" in err_out)
            )
            # check beat
            out_str = out_f.getvalue()
            self.assertIn("subprocess is still running", out_str)

            # check stdout
            out_str = out_str.replace("subprocess is still running\n", "")
            self.assertGreater(len(out_str.split("\n")), 15)  # check that more than 15 lines
