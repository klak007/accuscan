#!/bin/bash

# Pobranie aktualnej wersji (brancha)
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo "🔹 Aktualnie używasz wersji: $current_branch"

# Pobranie najnowszych danych z repozytorium
echo "🔄 Pobieram listę wersji oprogramowania z GitHub..."
git fetch --all --prune

# Pobranie listy zdalnych wersji w formacie `app-X.Y.Z`
latest_version=$(git branch -r | grep -Eo 'app-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/origin\///' | sort -V | tail -n 1)

# Jeśli nie znaleziono żadnej wersji, ustaw domyślną wersję
if [[ -z "$latest_version" ]]; then
    latest_version="app-1.0.0"
fi

echo "📌 Najnowsza dostępna wersja oprogramowania: $latest_version"

# Pobranie nazwy wersji do pobrania (propozycja: najnowsza wersja)
read -p "Podaj wersję oprogramowania do pobrania (ENTER = '$latest_version'): " selected_version

# Jeśli użytkownik nie podał wersji, wybieramy najnowszą
if [[ -z "$selected_version" ]]; then
    selected_version="$latest_version"
    echo "🔄 Używam najnowszej wersji: $selected_version"
fi

# Sprawdzenie, czy wersja istnieje lokalnie
if git show-ref --verify --quiet refs/heads/"$selected_version"; then
    echo "🟡 Przełączanie na wersję '$selected_version'..."
    git checkout "$selected_version"
else
    echo "🟡 Tworzenie nowej wersji '$selected_version' na podstawie zdalnego repozytorium..."
    git checkout -b "$selected_version" origin/"$selected_version"
fi

# Pytanie o pobranie zmian
read -p "Czy chcesz pobrać najnowsze zmiany dla tej wersji? (Y/n): " confirm
if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
    echo "❌ Anulowano operację."
    exit 0
fi

# Pobranie najnowszych zmian
git pull origin "$selected_version"

# Pokazanie aktualnego statusu repozytorium
echo "🟢 Aktualny status repozytorium po pobraniu zmian:"
git status

echo "✅ Wersja '$selected_version' została pobrana i przełączona!"
