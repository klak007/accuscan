#!/bin/bash
set -euo pipefail

# Kolory (opcjonalne)
YELLOW='\e[33m'
GREEN='\e[32m'
RED='\e[31m'
BLUE='\e[34m'
NC='\e[0m' # Reset

###################################
# Funkcja pomocy (--help)
###################################
function print_help() {
    echo "Użycie: $0 [opcje]"
    echo
    echo "Skrypt służy do pobierania (git pull) wybranej gałęzi w stylu GitHub Flow."
    echo "Najczęściej będzie to np. 'main', 'feature/nazwa' czy 'fix/...' itp."
    echo
    echo "Dostępne opcje:"
    echo "  --help            Wyświetla pomoc"
    echo "  --branch <nazwa>  Gałąź do pobrania (bez pytania interaktywnego)."
    exit 0
}

###################################
# Sprawdzenie, czy to repo Git
###################################
function check_if_git_repo() {
    if [[ ! -d .git ]]; then
        echo -e "${RED}[ERROR] Nie znaleziono katalogu .git. Przerywam...${NC}"
        exit 1
    fi
}

###################################
# Sprawdzenie niezacommitowanych zmian
###################################
function check_uncommitted_changes() {
    if [[ -n "$(git status --porcelain)" ]]; then
        echo -e "${YELLOW}[WARNING] Masz niezacommitowane zmiany. Czy na pewno kontynuować pull? (Y/n)${NC}"
        read -r response
        if [[ "$response" != "Y" && "$response" != "y" ]]; then
            echo -e "${RED}[ERROR] Operacja przerwana.${NC}"
            exit 1
        fi
    fi
}

###################################
# Parsowanie argumentów
###################################
selected_branch="" # Ustawimy, jeśli podano --branch
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help)
            print_help
            ;;
        --branch)
            selected_branch="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}[ERROR] Nieznana opcja: $1${NC}"
            exit 1
            ;;
    esac
done

###################################
# Wywołanie funkcji wstępnych
###################################
check_if_git_repo
check_uncommitted_changes

###################################
# Pobranie aktualnej gałęzi
###################################
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo -e "${BLUE}[INFO] Aktualna gałąź: ${NC}${YELLOW}$current_branch${NC}"

###################################
# Pobranie (fetch) najnowszych danych z repo
###################################
echo -e "${BLUE}[INFO] Pobieram najnowsze zmiany z origin...${NC}"
git fetch --all --prune

###################################
# Wybór gałęzi, jeśli nie podano --branch
###################################
if [[ -z "$selected_branch" ]]; then
    # Możesz tu np. ustawić domyślną gałąź "main", jeśli nie chcesz pytać
    # selected_branch="main"
    # Albo spytać użytkownika:
    echo -e "${BLUE}[INFO] Podaj nazwę gałęzi do pobrania (np. main, feature/xyz, fix/bug-123): ${NC}"
    read -r user_input
    if [[ -z "$user_input" ]]; then
        echo -e "${RED}[ERROR] Nie podano nazwy gałęzi. Przerywam.${NC}"
        exit 1
    fi
    selected_branch="$user_input"
fi

echo -e "${BLUE}[INFO] Wybrano gałąź: ${NC}${GREEN}$selected_branch${NC}"

###################################
# Sprawdzenie/utworzenie gałęzi lokalnie
###################################
if git show-ref --verify --quiet refs/heads/"$selected_branch"; then
    echo -e "${YELLOW}[WARNING] Przełączam się na istniejącą lokalnie gałąź '$selected_branch'.${NC}"
    git checkout "$selected_branch"
else
    if git ls-remote --exit-code origin "$selected_branch" &>/dev/null; then
        echo -e "${BLUE}[INFO] Gałąź '$selected_branch' istnieje na origin. Tworzę lokalną gałąź i przełączam się...${NC}"
        git checkout -b "$selected_branch" origin/"$selected_branch"
    else
        echo -e "${RED}[ERROR] Gałąź '$selected_branch' nie istnieje lokalnie ani na origin.${NC}"
        echo -e "${RED}[ERROR] Przerywam, bo nie ma czego pullować.${NC}"
        exit 1
    fi
fi

###################################
# Pull zmian
###################################
echo -e "${BLUE}[INFO] Czy chcesz pobrać najnowsze zmiany z '$selected_branch'? (Y/n): ${NC}"
read -r confirm
if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
    echo -e "${RED}[ERROR] Operacja anulowana.${NC}"
    exit 0
fi

git pull origin "$selected_branch"
echo -e "${GREEN}[INFO] Gałąź '$selected_branch' została zaktualizowana!${NC}"
git status
