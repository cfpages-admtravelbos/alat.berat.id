name: Manual Adsense Script Addition

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v2

      - name: Check if adsense.go exists
        run: |
          if [ -f "adsense.go" ]; then
            echo "adsense.go exists"
          else
            echo "adsense.go does not exist, exiting workflow."
            exit 1
          fi

      - name: Set up Go
        uses: actions/setup-go@v2
        with:
          go-version: '1.17'

      - name: Run Go Script
        run: go run adsense.go

      - name: Get Date
        id: date
        run: echo "::set-output name=date::$(date +'%Y-%m-%d')"

      - name: Check for Changes
        id: git_changes
        run: |
          if git diff --exit-code; then
            echo "::set-output name=changes::false"
          else
            echo "::set-output name=changes::true"
          fi

      - name: Commit and Push Changes
        if: steps.git_changes.outputs.changes == 'true'
        run: |
          git config --global user.email "github-actions@github.com"
          git config --global user.name "GitHub Actions"
          git add .
          git commit -m "Add Google Adsense script on ${{ steps.date.outputs.date }}"
          git push

      - name: Display Message if Nothing Changed
        if: steps.git_changes.outputs.changes == 'false'
        run: echo "Nothing changed, nothing to commit"
