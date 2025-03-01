#!/bin/bash

# Pobranie aktualnego brancha
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo "🔹 Aktualnie programujesz w branchu: $current_branch"

# Pobranie listy branchy i znalezienie najnowszego `app-X.Y.Z`
git fetch origin
latest_version=$(git branch -r | grep -Eo 'app-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/origin\///' | sort -t '-' -k2,2nr -k3,3nr -k4,4nr | head -n 1)

if [[ -z "$latest_version" ]]; then
    latest_version="app-1.0.0"
fi
echo "📌 Najnowsza wersja aplikacji: $latest_version"

# Pobranie tylko numeru wersji
version_number=$(echo "$latest_version" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+')

# Rozbicie wersji na części (bez ograniczeń)
major=$(echo "$version_number" | cut -d. -f1)
minor=$(echo "$version_number" | cut -d. -f2)
patch=$(echo "$version_number" | cut -d. -f3)

# Pobranie od użytkownika typu zmiany
echo "Jak duża jest ta zmiana?"
echo "1) 🔥 Duża (MAJOR) – zmienia kompatybilność"
echo "2) ✨ Średnia (MINOR) – nowe funkcje"
echo "3) 🛠️  Mała (PATCH) – poprawki"
read -p "Wybierz (1/2/3): " change_type

# Aktualizacja numeru wersji
case $change_type in
    1) ((major++)); minor=0; patch=0 ;;  # Resetujemy MINOR i PATCH po zmianie MAJOR
    2) ((minor++)); patch=0 ;;  # Resetujemy PATCH po zmianie MINOR
    3) ((patch++)) ;;  # Zwiększamy PATCH
    *) echo "❌ Niepoprawny wybór!"; exit 1 ;;
esac

# Generowanie nowej nazwy brancha
new_version="app-$major.$minor.$patch"
echo "📂 Tworzę nowy branch: $new_version"
git checkout -b "$new_version"

# Pokazanie statusu repozytorium
echo "🟡 Aktualny status repozytorium:"
git status

# Pytanie o commitowanie zmian
read -p "Czy chcesz dodać wszystkie zmiany i kontynuować? (Y/n): " confirm
if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
    echo "❌ Anulowano operację."
    exit 0
fi

# Dodanie wszystkich zmian
git add .

# Pobranie opisu commita (domyślnie "Małe poprawki" jeśli puste)
read -p "Podaj opis commita (ENTER = Małe poprawki): " commit_message
commit_message=${commit_message:-"Małe poprawki"}

# Wykonanie commita
git commit -m "$commit_message"

# Push nowego brancha na GitHuba
git push --set-upstream origin "$new_version"

echo "✅ Branch '$new_version' został utworzony i wypchnięty na GitHub!"
