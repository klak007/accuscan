#!/bin/bash
set -euo pipefail

# Kolorowanie
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
    echo "Skrypt służy do pobierania (pull) wybranego brancha w formacie app-X.Y.Z."
    echo
    echo "Dostępne opcje:"
    echo "  --help            Wyświetla pomoc"
    echo "  --branch <nazwa>  Od razu pobiera wskazaną wersję (branch) bez pytania"
    exit 0
}

###################################
# Funkcja sprawdzająca .git
###################################
function check_if_git_repo() {
    if [[ ! -d .git ]]; then
        echo -e "${RED}[ERROR] Ten katalog nie wygląda na repozytorium Git. Przerywam...${NC}"
        exit 1
    fi
}

###################################
# Funkcja sprawdzająca niezacommitowane zmiany
###################################
function check_uncommitted_changes() {
    if [[ -n "$(git status --porcelain)" ]]; then
        echo -e "${YELLOW}[WARNING] Masz niezacommitowane zmiany. Czy na pewno kontynuować pull? (Y/n)${NC}"
        read -r response
        if [[ "$response" != "Y" && "$response" != "y" ]]; then
            echo -e "${RED}[ERROR] Operacja przerwana.${NC}"
            exit 0
        fi
    fi
}

###################################
# Parsowanie argumentów
###################################
selected_version="" # Może być ustawiona przez --branch
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help)
            print_help
            ;;
        --branch)
            selected_version="$2"
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
echo -e "${BLUE}[INFO] Aktualnie używasz gałęzi:${NC} ${YELLOW}$current_branch${NC}"

# Pobranie najnowszych danych z repo
echo -e "${BLUE}[INFO] Pobieram listę wersji z GitHub...${NC}"
git fetch --all --prune

# Znalezienie najnowszego branchu w formacie app-X.Y.Z
latest_version=$(git branch -r | grep -Eo 'app-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/origin\///' | sort -V | tail -n 1)

if [[ -z "$latest_version" ]]; then
    latest_version="app-1.0.0"
fi

echo -e "${BLUE}[INFO] Najnowsza dostępna wersja:${NC} ${GREEN}$latest_version${NC}"

###################################
# Wybór wersji do pobrania
###################################
function choose_version_if_needed() {
    if [[ -z "$selected_version" ]]; then
        # Zapytaj użytkownika w trybie interaktywnym
        read -p "$(echo -e \"${BLUE}Podaj wersję do pobrania (ENTER = '$latest_version'): ${NC}\")" user_input
        if [[ -z "$user_input" ]]; then
            selected_version="$latest_version"
        else
            selected_version="$user_input"
        fi
        echo -e "${BLUE}[INFO] Wybrano wersję:${NC} ${GREEN}$selected_version${NC}"
    fi
}

choose_version_if_needed

###################################
# Funkcja do przełączenia gałęzi
###################################
function switch_branch() {
    if git show-ref --verify --quiet refs/heads/"$selected_version"; then
        echo -e "${YELLOW}[WARNING] Przełączanie na lokalną gałąź:${NC} $selected_version"
        git checkout "$selected_version"
    else
        echo -e "${YELLOW}[WARNING] Tworzenie nowej gałęzi '${selected_version}' z origin...${NC}"
        git checkout -b "$selected_version" origin/"$selected_version"
    fi
}

switch_branch

###################################
# Funkcja do pull
###################################
function pull_changes() {
    read -p "$(echo -e \"${BLUE}Czy chcesz pobrać najnowsze zmiany (pull) z '$selected_version'? (Y/n): ${NC}\")" confirm
    if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
        echo -e "${RED}[ERROR] Operacja anulowana.${NC}"
        exit 0
    fi

    git pull origin "$selected_version"
    echo -e "${GREEN}[INFO] Wersja '$selected_version' została pobrana i przełączona!${NC}"
    git status
}

pull_changes
