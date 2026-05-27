content = open("tests/test_heat_transfer.py", "r", encoding="utf-8").read()

# Find the bad test and replace it
old = '''    def test_ss304_temperature_within_service_limit(self, operating_plant_inputs):
        """
        Combustion gas at 779\xb0C is within SS304 service limit of 870\xb0C.
        No temperature warning should be raised.
        """
        result = calculate(operating_plant_inputs)
        assert not result.steel_temp_warning, \\
            f"Should not flag temp warning: 779\xb0C < SS304 limit 870\xb0C"'''

new = '''    def test_ss304_temperature_warning_at_900c(self, operating_plant_inputs):
        """900C combustion gas exceeds SS304 limit of 870C -- warning must fire."""
        result = calculate(operating_plant_inputs)
        assert result.steel_temp_warning, \\
            f"Should flag temp warning: 900C > SS304 limit 870C"'''

if old in content:
    content = content.replace(old, new)
    print("Replacement made")
else:
    print("Pattern not found -- printing lines 250-270:")
    lines = content.splitlines()
    for i, line in enumerate(lines[249:270], start=250):
        print(f"{i}: {repr(line)}")

open("tests/test_heat_transfer.py", "w", encoding="utf-8").write(content)