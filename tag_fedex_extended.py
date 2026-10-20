name: Tag ShipStation orders by ZIP

on:
  schedule:
    # Every 5 minutes = the fastest GitHub allows. Free and unlimited ONLY on a PUBLIC repo.
    # If your repo is PRIVATE, change this to "*/30 * * * *" to stay under the 2,000 free minutes/month.
    - cron: "*/5 * * * *"
  workflow_dispatch:             # lets you run it manually from the Actions tab
    inputs:
      apply:
        description: "Actually tag orders? (false = dry run)"
        default: "false"

concurrency:
  group: tag-orders
  cancel-in-progress: false      # never run two at once

jobs:
  tag:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install requests
      - name: Run tagger
        env:
          SHIPSTATION_KEY: ${{ secrets.SHIPSTATION_KEY }}
          SHIPSTATION_SECRET: ${{ secrets.SHIPSTATION_SECRET }}
          TAG_NAME: ${{ vars.TAG_NAME }}
          APPLY: ${{ github.event_name == 'schedule' && 'true' || inputs.apply }}
        run: |
          if [ "$APPLY" = "true" ]; then
            python tag_orders.py --apply
          else
            python tag_orders.py
          fi

      - name: Run FedEx extended residence tagger
        if: ${{ !cancelled() }}
        env:
          SHIPSTATION_API_KEY: ${{ secrets.SHIPSTATION_KEY }}
          SHIPSTATION_API_SECRET: ${{ secrets.SHIPSTATION_SECRET }}
          APPLY: ${{ github.event_name == 'schedule' && 'true' || inputs.apply }}
        run: |
          if [ "$APPLY" = "true" ]; then
            python tag_fedex_extended.py --apply
          else
            python tag_fedex_extended.py
          fi
