#!/bin/bash

# Definicje kolorów
YELLOW='\e[33m'
GREEN='\e[32m'
RED='\e[31m'
BLUE='\e[34m'
NC='\e[0m' # Resetowanie koloru

# Pobranie aktualnej wersji (brancha)
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo -e "${BLUE}🔹 Aktualnie używasz wersji:${NC} ${YELLOW}$current_branch${NC}"

# Pobranie najnowszych danych z repozytorium
echo -e "${BLUE}🔄 Pobieram listę wersji oprogramowania z GitHub...${NC}"
git fetch --all --prune

# Pobranie listy zdalnych wersji w formacie `app-X.Y.Z`
latest_version=$(git branch -r | grep -Eo 'app-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/origin\///' | sort -V | tail -n 1)

# Jeśli nie znaleziono żadnej wersji, ustaw domyślną wersję
if [[ -z "$latest_version" ]]; then
    latest_version="app-1.0.0"
fi

echo -e "${BLUE}📌 Najnowsza dostępna wersja oprogramowania:${NC} ${GREEN}$latest_version${NC}"

# Pobranie nazwy wersji do pobrania (propozycja: najnowsza wersja)
read -p "$(echo -e "${BLUE}Podaj wersję oprogramowania do pobrania${NC} (ENTER = '${GREEN}$latest_version${NC}'): ")" selected_version

# Jeśli użytkownik nie podał wersji, wybieramy najnowszą
if [[ -z "$selected_version" ]]; then
    selected_version="$latest_version"
    echo -e "${BLUE}🔄 Używam najnowszej wersji:${NC} ${GREEN}$selected_version${NC}"
fi

# Sprawdzenie, czy wersja istnieje lokalnie
if git show-ref --verify --quiet refs/heads/"$selected_version"; then
    echo -e "${YELLOW}🟡 Przełączanie na wersję:${NC} $selected_version..."
    git checkout "$selected_version"
else
    echo -e "${YELLOW}🟡 Tworzenie nowej wersji:${NC} $selected_version na podstawie zdalnego repozytorium..."
    git checkout -b "$selected_version" origin/"$selected_version"
fi

# Pytanie o pobranie zmian
read -p "$(echo -e "${BLUE}Czy chcesz pobrać najnowsze zmiany dla tej wersji?${NC} (Y/n): ")" confirm
if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
    echo -e "${RED}❌ Anulowano operację.${NC}"
    exit 0
fi

# Pobranie najnowszych zmian
git pull origin "$selected_version"

# Pokazanie aktualnego statusu repozytorium
echo -e "${GREEN}🟢 Aktualny status repozytorium po pobraniu zmian:${NC}"
git status

echo -e "${GREEN}✅ Wersja '$selected_version' została pobrana i przełączona!${NC}"
