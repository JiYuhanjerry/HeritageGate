# HeritageGate v0.2.0 Windows quick start

Open PowerShell in the extracted `HeritageGate` directory.

## Development installation

```powershell
python -m pip install -e .
python -c "import heritagegate; print(heritagegate.__version__)"
```

Expected version:

```text
0.2.0
```

## Run all tests

```powershell
python -m unittest discover -s .\tests -v
```

Expected result:

```text
Ran 16 tests
OK
```

## Run the normalized demonstration

```powershell
Remove-Item .\structured_demo.db, .\structured_manifest.json `
    -Force -ErrorAction SilentlyContinue

python .\run_heritagegate.py --db .\structured_demo.db structured-demo |
    Set-Content -Encoding utf8 .\structured_manifest.json
```

## Verify the result

```powershell
Select-String -Path .\structured_manifest.json -Pattern '"status": "completed"'
Select-String -Path .\structured_manifest.json -Pattern '"schema_version": "0.2.0"'
```

Inspect entity counts:

```powershell
python -c "import json; m=json.load(open('structured_manifest.json', encoding='utf-8-sig')); print({k: len(v) for k,v in m['structured_entities'].items()})"
```

Expected output:

```text
{'rights_holders': 3, 'authorization_records': 1,
 'cultural_element_cards': 2, 'model_runs': 1,
 'expert_reviews': 3, 'market_tests': 1,
 'revenue_distributions': 1}
```
