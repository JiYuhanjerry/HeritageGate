.PHONY: test structured-demo pilot-demo web export-research export-softwarex clean

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

structured-demo:
	heritagegate --db structured_demo.db structured-demo > structured_manifest.json

pilot-demo:
	heritagegate --db pilot_demo.db pilot-demo --project-id demo-pilot-001 > pilot_demo_output.json

web:
	heritagegate --db pilot_demo.db web --open-browser

export-research:
	heritagegate --db pilot_demo.db export-research demo-pilot-001 heritagegate_research_bundle.zip

export-softwarex:
	heritagegate --db pilot_demo.db export-softwarex-evidence demo-pilot-001 heritagegate_softwarex_evidence.zip

clean:
	rm -rf build dist *.egg-info *.db *.json *.zip
