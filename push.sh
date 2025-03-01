#!/bin/bash

# Pobranie aktualnego brancha
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo "🔹 Aktualnie programujesz w branchu: $current_branch"

# Pobranie pełnej listy branchy z GitHuba (lokalne + zdalne)
git fetch --all --prune
latest_version=$(git branch -r | grep -Eo 'app-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/origin\///' | sort -V | tail -n 1)

# Jeśli nie znaleziono żadnego brancha, ustaw domyślną wersję
if [[ -z "$latest_version" ]]; then
    latest_version="app-1.0.0"
fi

echo "📌 Najnowsza wersja aplikacji: $latest_version"

# Pobranie numeru wersji
version_number=$(echo "$latest_version" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+')

# Rozbicie wersji na MAJOR, MINOR, PATCH
major=$(echo "$version_number" | cut -d. -f1)
minor=$(echo "$version_number" | cut -d. -f2)
patch=$(echo "$version_number" | cut -d. -f3)

# Pobranie od użytkownika typu zmiany
echo "Jak duża jest ta zmiana?"
echo "1) 🔥 Duża (MAJOR) – zmienia kompatybilność"
echo "2) ✨ Średnia (MINOR) – nowe funkcje"
echo "3) 🛠️  Mała (PATCH) – poprawki"
read -p "Wybierz (1/2/3): " change_type

# Domyślna wiadomość commita
commit_message=""

# Aktualizacja numeru wersji na podstawie wyboru
case $change_type in
    1) ((major++)); minor=0; patch=0; commit_message="🔥 Duża aktualizacja oprogramowania" ;;
    2) ((minor++)); commit_message="✨ Nowe funkcjonalności" ;;
    3) ((patch++)); commit_message="🛠️  Łatanie błędów, drobne poprawki" ;;
    *) echo "❌ Niepoprawny wybór!"; exit 1 ;;
esac

# Generowanie nowej nazwy brancha
new_version="app-$major.$minor.$patch"

# Sprawdzenie, czy branch już istnieje lokalnie
if git show-ref --verify --quiet refs/heads/"$new_version"; then
    echo "⚠️ Branch '$new_version' już istnieje! Przełączam się na niego."
    git checkout "$new_version"
else
    echo "📂 Tworzę nowy branch: $new_version"
    git checkout -b "$new_version"
fi

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

# Pobranie opisu commita od użytkownika (ENTER = domyślny commit)
read -p "Podaj opis commita (ENTER = '$commit_message'): " user_commit
commit_message=${user_commit:-$commit_message}

# Wykonanie commita
git commit -m "$commit_message"

# Push nowego brancha na GitHuba
git push --set-upstream origin "$new_version"

echo "✅ Branch '$new_version' został utworzony i wypchnięty na GitHub!"
