#!/bin/bash
set -euo pipefail

# Kolorowanie (opcjonalne)
YELLOW='\e[33m'
GREEN='\e[32m'
RED='\e[31m'
BLUE='\e[34m'
NC='\e[0m' # Reset koloru

# 1. Sprawdzenie, czy to katalog z repozytorium Git
if [[ ! -d .git ]]; then
    echo -e "${RED}[ERROR] Ten katalog nie wygląda na repozytorium Git. Przerywam...${NC}"
    exit 1
fi

# 2. Sprawdzenie, czy są niezacommitowane zmiany
if [[ -n "$(git status --porcelain)" ]]; then
    echo -e "${YELLOW}[WARNING] Masz niezacommitowane zmiany. Czy na pewno kontynuować? (Y/n)${NC}"
    read -r response
    if [[ "$response" != "Y" && "$response" != "y" ]]; then
        echo -e "${RED}[ERROR] Operacja przerwana.${NC}"
        exit 0
    fi
fi

# Pobranie aktualnego brancha
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo -e "${BLUE}[INFO] Aktualnie pracujesz w wersji:${NC} ${YELLOW}$current_branch${NC}"

# Pobranie pełnej listy branchy z GitHuba (lokalne + zdalne)
git fetch --all --prune
latest_version=$(git branch -r | grep -Eo 'app-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/origin\///' | sort -V | tail -n 1)

# Jeśli nie znaleziono żadnego brancha w formacie app-X.Y.Z, ustaw domyślny
if [[ -z "$latest_version" ]]; then
    latest_version="app-1.0.0"
fi

echo -e "${BLUE}[INFO] Najnowsza wersja aplikacji:${NC} ${GREEN}$latest_version${NC}"

# Wyciągnięcie numeru wersji
version_number=$(echo "$latest_version" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+')

# Rozbicie wersji na MAJOR, MINOR, PATCH
major=$(echo "$version_number" | cut -d. -f1)
minor=$(echo "$version_number" | cut -d. -f2)
patch=$(echo "$version_number" | cut -d. -f3)

# Pobranie od użytkownika rodzaju zmiany
echo -e "${BLUE}Jak duża jest zmiana?${NC}"
echo -e "${YELLOW}1) Duża (MAJOR) – zmienia kompatybilność${NC}"
echo -e "${YELLOW}2) Średnia (MINOR) – nowe funkcje${NC}"
echo -e "${YELLOW}3) Mała (PATCH) – poprawki${NC}"
read -p "$(echo -e "${BLUE}Wybierz (1/2/3): ${NC}")" change_type

# Domyślna wiadomość commita
commit_message=""

case $change_type in
    1)
        ((major++))
        minor=0
        patch=0
        commit_message="Big changes"
        ;;
    2)
        ((minor++))
        commit_message="New functionalities"
        ;;
    3)
        ((patch++))
        commit_message="Bug fixes"
        ;;
    *)
        echo -e "${RED}[ERROR] Niepoprawny wybór!${NC}"
        exit 1
        ;;
esac

# Generowanie nowej nazwy brancha
new_version="app-$major.$minor.$patch"

# Sprawdzenie, czy branch już istnieje lokalnie
if git show-ref --verify --quiet refs/heads/"$new_version"; then
    echo -e "${YELLOW}[WARNING] Branch '$new_version' już istnieje! Przełączam się na niego.${NC}"
    git checkout "$new_version"
else
    echo -e "${BLUE}[INFO] Tworzę nowy branch:${NC} ${GREEN}$new_version${NC}"
    git checkout -b "$new_version"
fi

# Pokazanie statusu repozytorium
echo -e "${YELLOW}[WARNING] Aktualny status repozytorium:${NC}"
git status

# Pytanie o commitowanie zmian
read -p "$(echo -e "${BLUE}Czy chcesz dodać wszystkie zmiany i kontynuować? (Y/n): ${NC}")" confirm
if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
    echo -e "${RED}[ERROR] Operacja anulowana.${NC}"
    exit 0
fi

# Dodanie wszystkich zmian
git add .

# Pobranie opisu commita od użytkownika (ENTER = domyślny commit)
read -p "$(echo -e "${BLUE}Podaj opis commita${NC} (ENTER = '${GREEN}$commit_message${NC}'): ")" user_commit
commit_message=${user_commit:-$commit_message}

# Wykonanie commita
git commit -m "$commit_message"

# Zapytanie o tagowanie wersji
echo -e "${BLUE}[INFO] Czy utworzyć tag dla tej wersji? (Y/n)${NC}"
read -r create_tag
if [[ "$create_tag" == "Y" || "$create_tag" == "y" ]]; then
    tag_name="v$major.$minor.$patch"
    git tag -a "$tag_name" -m "Release $tag_name"
    git push origin "$tag_name"
    echo -e "${GREEN}[INFO] Utworzono i wypchnięto tag '$tag_name'${NC}"
fi

# Push nowego brancha na GitHuba
git push --set-upstream origin "$new_version"

echo -e "${GREEN}[INFO] Branch '$new_version' został utworzony i wypchnięty na GitHub!${NC}"
