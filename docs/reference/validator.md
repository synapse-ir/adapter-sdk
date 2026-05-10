# AdapterValidator

Validates an adapter against all 13 conformance rules.

## Usage


```python
from synapse_sdk import AdapterValidator
from my_module import MyAdapter

validator = AdapterValidator(MyAdapter())
result = validator.run()
print(result.passed)
print(result.errors)

validator.assert_valid()

# Run a specific fixture through the adapter
from synapse_sdk.testing.fixtures import ALL_FIXTURES
validator.assert_valid_on(ALL_FIXTURES[0])

# Parametrize across all 20 fixtures in pytest
import pytest
@pytest.mark.parametrize("fixture", ALL_FIXTURES)
def test_all_fixtures(fixture):
    AdapterValidator(MyAdapter()).assert_valid_on(fixture)
```



## CLI


```bash
synapse-validate --adapter my_module.MyAdapter
synapse-validate --adapter my_module.MyAdapter --all-fixtures
synapse-validate --adapter my_module.MyAdapter --fixture path/to/fixture.json
```


