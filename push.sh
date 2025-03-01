#!/bin/bash
set -euo pipefail

# Kolorowanie (opcjonalne)
YELLOW='\e[33m'
GREEN='\e[32m'
RED='\e[31m'
BLUE='\e[34m'
NC='\e[0m'

###################################
# Funkcja pomocy
###################################
print_help() {
    echo "Użycie: $0 [opcje]"
    echo
    echo "Skrypt tworzy (lub przełącza się na) gałąź w stylu GitHub Flow (np. feature/...)."
    echo "Następnie pozwala zacommitować i wypchnąć zmiany do repozytorium zdalnego."
    echo
    echo "Dostępne opcje:"
    echo "  --help    Wyświetla tę pomoc"
    exit 0
}

###################################
# Sprawdzanie argumentów
###################################
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help)
            print_help
            ;;
        *)
            echo -e "${RED}[ERROR] Nieznana opcja: $1${NC}"
            exit 1
            ;;
    esac
done

###################################
# Sprawdzanie, czy to repo Git
###################################
if [[ ! -d .git ]]; then
    echo -e "${RED}[ERROR] Nie znaleziono katalogu .git. Przerywam...${NC}"
    exit 1
fi

###################################
# Sprawdzanie niezacommitowanych zmian
###################################
if [[ -n "$(git status --porcelain)" ]]; then
    echo -e "${YELLOW}[WARNING] Masz niezacommitowane zmiany. Czy na pewno kontynuować? (Y/n)${NC}"
    read -r response
    if [[ "$response" != "Y" && "$response" != "y" ]]; then
        echo -e "${RED}[ERROR] Operacja przerwana.${NC}"
        exit 1
    fi
fi

###################################
# Pobranie obecnej gałęzi
###################################
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo -e "${BLUE}[INFO] Aktualna gałąź: ${NC}${YELLOW}$current_branch${NC}"

###################################
# Aktualizacja repo (git pull)
###################################
echo -e "${BLUE}[INFO] Aktualizuję gałąź '$current_branch' z origin...${NC}"
git fetch --all --prune
git pull origin "$current_branch"

###################################
# Pytanie o nazwę nowej gałęzi
###################################
echo -e "${BLUE}[INFO] Podaj nazwę nowej gałęzi (np. feature/moj-feature, fix/poprawka): ${NC}"
read -r new_branch_name
if [[ -z "$new_branch_name" ]]; then
    echo -e "${RED}[ERROR] Nie podano nazwy. Przerywam.${NC}"
    exit 1
fi

###################################
# Tworzenie/przełączanie się na nową gałąź
###################################
# Sprawdzamy, czy lokalnie już istnieje
if git show-ref --verify --quiet refs/heads/"$new_branch_name"; then
    # Istnieje lokalnie
    echo -e "${YELLOW}[WARNING] Gałąź '$new_branch_name' istnieje już lokalnie. Przełączam się.${NC}"
    git checkout "$new_branch_name"
else
    # Sprawdzamy, czy istnieje na origin
    if git ls-remote --exit-code origin "$new_branch_name" &>/dev/null; then
        echo -e "${YELLOW}[WARNING] Gałąź '$new_branch_name' istnieje na origin. Pobieram ją lokalnie.${NC}"
        git checkout -b "$new_branch_name" origin/"$new_branch_name"
    else
        # Tworzymy nową
        echo -e "${BLUE}[INFO] Tworzę nową gałąź '$new_branch_name' od '$current_branch'.${NC}"
        git checkout -b "$new_branch_name"
    fi
fi

###################################
# Dodawanie i commit zmian
###################################
echo -e "${BLUE}[INFO] Czy chcesz dodać wszystkie zmiany i zacommitować? (Y/n): ${NC}"
read -r confirm
if [[ "$confirm" == "Y" || "$confirm" == "y" ]]; then
    git add .
    echo -e "${BLUE}[INFO] Podaj wiadomość commita (ENTER = 'Work in progress'): ${NC}"
    read -r commit_message
    commit_message=${commit_message:-"Work in progress"}
    git commit -m "$commit_message"
    echo -e "${GREEN}[INFO] Zmiany zacommitowane lokalnie.${NC}"
else
    echo -e "${YELLOW}[WARNING] Pomijam commit. Możesz wykonać go samodzielnie później.${NC}"
fi

###################################
# Push nowej gałęzi
###################################
echo -e "${BLUE}[INFO] Czy wypchnąć gałąź '$new_branch_name' na origin? (Y/n): ${NC}"
read -r push_confirm
if [[ "$push_confirm" == "Y" || "$push_confirm" == "y" ]]; then
    git push --set-upstream origin "$new_branch_name"
    echo -e "${GREEN}[INFO] Gałąź '$new_branch_name' została wypchnięta na GitHub!${NC}"
else
    echo -e "${YELLOW}[WARNING] Nie wypchnięto gałęzi. Zrobisz to później, np. 'git push --set-upstream origin <branch>'.${NC}"
fi

echo -e "${GREEN}[INFO] Gotowe! Teraz możesz otworzyć Pull Request do 'main' (lub innej gałęzi).${NC}"
