#!/bin/bash
#
# scripts/delete_products.sh
#
# Delete COG products and optional log files up to a specified date.
#
# Usage:
#   ./scripts/delete_products.sh 20260101
#   ./scripts/delete_products.sh 20260101 --radars RMA1,RMA2
#   ./scripts/delete_products.sh 20260101 --product DBZH
#   ./scripts/delete_products.sh 20260101 --remove-logs
#   ./scripts/delete_products.sh 20260101 --radars RMA1 --product DBZH --remove-logs --dry-run
#
# This script:
# 1. Takes a date (YYYYMMDD) as the cutoff for deletion
# 2. Passes any additional flags to the delete command
# 3. Executes the delete command inside the indexer container
# 4. Exits with appropriate status code

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_usage() {
    cat <<EOF
Usage: $0 DATE [OPTIONS]

Delete COG products and optional log files from the webmet25 stack up to a specified date.

Positional arguments:
  DATE                     Date in YYYYMMDD format (e.g., 20260101).
                          All COGs with observation_time <= this date will be deleted.

Optional arguments:
  --radars RADAR_LIST      Comma-separated list of radar codes (e.g., RMA1,RMA2,RMA6).
                          If omitted, all radars are included.
  --product PRODUCT_KEY    Delete only this product (e.g., DBZH).
                          If omitted, all products are deleted.
  --remove-logs            Also delete matching log files (genpro25.log.YYYY-MM-DD).
                          Never deletes the current genpro25.log file.
  --quiet                  Suppress per-file logging. Only show the deletion summary.
  --dry-run                Show what would be deleted without actually deleting.

Examples:
  # Delete all products up to Jan 1, 2026
  $0 20260101

  # Delete products only from RMA1 and RMA2
  $0 20260101 --radars RMA1,RMA2

  # Delete only DBZH product
  $0 20260101 --product DBZH

  # Combine filters: RMA1 + RMA2 + DBZH
  $0 20260101 --radars RMA1,RMA2 --product DBZH

  # Also delete log files matching the date
  $0 20260101 --remove-logs

  # Delete COGs and logs from specific radars only
  $0 20260101 --radars RMA1,RMA6 --remove-logs

  # Suppress verbose output, only show summary
  $0 20260101 --quiet

  # Combine: delete logs and COGs with minimal output
  $0 20260101 --remove-logs --quiet

  # Preview deletion without actually deleting
  $0 20260101 --dry-run

EOF
    exit 1
}

# Check arguments
if [[ $# -lt 1 ]]; then
    print_usage
fi

DATE="$1"
shift

# Verify Docker Compose is available
if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}Error: docker-compose is not available${NC}"
    echo "Please ensure Docker Compose is installed and in your PATH."
    exit 1
fi

# Verify indexer service exists
if ! docker compose -f "$PROJECT_ROOT/docker-compose.yml" ps indexer &> /dev/null; then
    echo -e "${RED}Error: indexer service is not running${NC}"
    echo "Start the stack with: docker compose up -d"
    exit 1
fi

# Build the command
CMD="python -m indexer.manage delete $DATE"

# Append additional arguments if provided
while [[ $# -gt 0 ]]; do
    case "$1" in
        --radars)
            CMD="$CMD --radars $2"
            shift 2
            ;;
        --product)
            CMD="$CMD --product $2"
            shift 2
            ;;
        --remove-logs)
            CMD="$CMD --remove-logs"
            shift
            ;;
        --quiet)
            CMD="$CMD --quiet"
            shift
            ;;
        --dry-run)
            CMD="$CMD --dry-run"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            print_usage
            ;;
    esac
done

# Display what we're about to do
echo -e "${YELLOW}Executing deletion command in indexer container...${NC}"
echo "Command: $CMD"
echo ""

# Execute the command
if docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T indexer $CMD; then
    echo ""
    echo -e "${GREEN}✓ Command completed successfully${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}✗ Command failed${NC}"
    exit 1
fi
