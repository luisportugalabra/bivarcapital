#!/bin/bash
cd ~/bivarcapital
echo "Updating momentum signal..."
python3 scripts/momentum_signal.py
echo ""
echo "Pushing to site..."
git add momentum-data.json
git commit -m "Update momentum signal $(date +%Y-%m-%d)"
git push
echo ""
echo "Done. Site will update in ~1 min."
read -p "Press Enter to close."
