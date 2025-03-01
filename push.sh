#!/bin/bash

# Definicje kolorów
YELLOW='\e[33m'
GREEN='\e[32m'
RED='\e[31m'
BLUE='\e[34m'
NC='\e[0m' # Resetowanie koloru

# Pobranie aktualnego brancha
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo -e "${BLUE}🔹 Aktualnie programujesz w wersji:${NC} ${YELLOW}$current_branch${NC}"

# Pobranie pełnej listy branchy z GitHuba (lokalne + zdalne)
git fetch --all --prune
latest_version=$(git branch -r | grep -Eo 'app-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/origin\///' | sort -V | tail -n 1)

# Jeśli nie znaleziono żadnego brancha, ustaw domyślną wersję
if [[ -z "$latest_version" ]]; then
    latest_version="app-1.0.0"
fi

echo -e "${BLUE}📌 Najnowsza wersja aplikacji:${NC} ${GREEN}$latest_version${NC}"

# Pobranie numeru wersji
version_number=$(echo "$latest_version" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+')

# Rozbicie wersji na MAJOR, MINOR, PATCH
major=$(echo "$version_number" | cut -d. -f1)
minor=$(echo "$version_number" | cut -d. -f2)
patch=$(echo "$version_number" | cut -d. -f3)

# Pobranie od użytkownika typu zmiany
echo -e "${BLUE}Jak duża jest ta zmiana?${NC}"
echo -e "${YELLOW}1) 🔥 Duża (MAJOR) – zmienia kompatybilność${NC}"
echo -e "${YELLOW}2) ✨ Średnia (MINOR) – nowe funkcje${NC}"
echo -e "${YELLOW}3) 🛠️  Mała (PATCH) – poprawki${NC}"
read -p "$(echo -e "${BLUE}Wybierz (1/2/3): ${NC}")" change_type

# Domyślna wiadomość commita
commit_message=""

# Aktualizacja numeru wersji na podstawie wyboru
case $change_type in
    1) ((major++)); minor=0; patch=0; commit_message="🔥 Duża aktualizacja oprogramowania" ;;
    2) ((minor++)); commit_message="✨ Nowe funkcjonalności" ;;
    3) ((patch++)); commit_message="🛠️  Łatanie błędów, drobne poprawki" ;;
    *) echo -e "${RED}❌ Niepoprawny wybór!${NC}"; exit 1 ;;
esac

# Generowanie nowej nazwy brancha
new_version="app-$major.$minor.$patch"

# Sprawdzenie, czy branch już istnieje lokalnie
if git show-ref --verify --quiet refs/heads/"$new_version"; then
    echo -e "${YELLOW}⚠️ Branch '$new_version' już istnieje! Przełączam się na niego.${NC}"
    git checkout "$new_version"
else
    echo -e "${BLUE}📂 Tworzę nowy branch:${NC} ${GREEN}$new_version${NC}"
    git checkout -b "$new_version"
fi

# Pokazanie statusu repozytorium
echo -e "${YELLOW}🟡 Aktualny status repozytorium:${NC}"
git status

# Pytanie o commitowanie zmian
read -p "$(echo -e "${BLUE}Czy chcesz dodać wszystkie zmiany i kontynuować?${NC} (Y/n): ")" confirm
if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
    echo -e "${RED}❌ Anulowano operację.${NC}"
    exit 0
fi

# Dodanie wszystkich zmian
git add .

# Pobranie opisu commita od użytkownika (ENTER = domyślny commit)
read -p "$(echo -e "${BLUE}Podaj opis commita${NC} (ENTER = '${GREEN}$commit_message${NC}'): ")" user_commit
commit_message=${user_commit:-$commit_message}

# Wykonanie commita
git commit -m "$commit_message"

# Push nowego brancha na GitHuba
git push --set-upstream origin "$new_version"

echo -e "${GREEN}✅ Branch '$new_version' został utworzony i wypchnięty na GitHub!${NC}"
