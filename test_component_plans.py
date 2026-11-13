import unittest
from component_plans import planned_components


class ComponentPlansTest(unittest.TestCase):
    def test_mcu_is_display_only_and_keeps_extensible_capabilities(self):
        mcu=next(item for item in planned_components() if item["id"]=="mcu")
        self.assertTrue(mcu["planned"])
        self.assertFalse(mcu["enabled"])
        self.assertNotIn("entrypoint",mcu)
        for capability in ("ADC","DAC","UART","SPI","PWM"):
            self.assertIn(capability,mcu["capabilities"])
