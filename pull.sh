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

# 2. Sprawdzenie, czy są niezacommitowane zmiany (zapobiega nadpisaniu)
if [[ -n "$(git status --porcelain)" ]]; then
    echo -e "${YELLOW}[WARNING] Masz niezacommitowane zmiany. Czy na pewno kontynuować pull? (Y/n)${NC}"
    read -r response
    if [[ "$response" != "Y" && "$response" != "y" ]]; then
        echo -e "${RED}[ERROR] Operacja przerwana.${NC}"
        exit 0
    fi
fi

# Pobranie aktualnej wersji (brancha)
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo -e "${BLUE}[INFO] Aktualnie używasz wersji:${NC} ${YELLOW}$current_branch${NC}"

# Pobranie najnowszych danych z repozytorium
echo -e "${BLUE}[INFO] Pobieram listę wersji oprogramowania z GitHub...${NC}"
git fetch --all --prune

# Znalezienie najnowszego branchu w formacie app-X.Y.Z
latest_version=$(git branch -r | grep -Eo 'app-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/origin\///' | sort -V | tail -n 1)

# Jeśli nie znaleziono żadnej wersji, ustaw domyślną
if [[ -z "$latest_version" ]]; then
    latest_version="app-1.0.0"
fi

echo -e "${BLUE}[INFO] Najnowsza dostępna wersja oprogramowania:${NC} ${GREEN}$latest_version${NC}"

# Pobranie od użytkownika wersji do pobrania
read -p "$(echo -e "${BLUE}Podaj wersję oprogramowania do pobrania (ENTER = '${GREEN}$latest_version${NC}'): ${NC}")" selected_version

if [[ -z "$selected_version" ]]; then
    selected_version="$latest_version"
    echo -e "${BLUE}[INFO] Używam najnowszej wersji:${NC} ${GREEN}$selected_version${NC}"
fi

# Sprawdzenie, czy wersja istnieje lokalnie
if git show-ref --verify --quiet refs/heads/"$selected_version"; then
    echo -e "${YELLOW}[WARNING] Przełączanie na wersję:${NC} $selected_version..."
    git checkout "$selected_version"
else
    echo -e "${YELLOW}[WARNING] Tworzenie lokalnej gałęzi '${NC}$selected_version${YELLOW}' z repozytorium zdalnego...${NC}"
    git checkout -b "$selected_version" origin/"$selected_version"
fi

# Pytanie o pobranie najnowszych zmian
read -p "$(echo -e "${BLUE}Czy chcesz pobrać najnowsze zmiany dla tej wersji? (Y/n): ${NC}")" confirm
if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
    echo -e "${RED}[ERROR] Operacja anulowana.${NC}"
    exit 0
fi

# Pobranie najnowszych zmian z repozytorium
git pull origin "$selected_version"

# Pokazanie aktualnego statusu
echo -e "${GREEN}[INFO] Status repozytorium po pobraniu zmian:${NC}"
git status

echo -e "${GREEN}[INFO] Wersja '$selected_version' została pobrana i przełączona!${NC}"
