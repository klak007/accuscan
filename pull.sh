#!/bin/bash

# Pobranie aktualnego brancha
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo "🔹 Aktualnie programujesz w branchu: $current_branch"

# Pobranie najnowszych danych z repozytorium
echo "🔄 Pobieram listę branchy z GitHub..."
git fetch origin

# Pobranie listy lokalnych branchy
local_branches=$(git branch | sed 's/^..//')

# Pobranie listy zdalnych branchy
remote_branches=$(git branch -r | grep -v '\->' | sed 's/origin\///')

echo ""
echo "🗂️  **Dostępne branche:**"
echo "📂 **Lokalne branche:**"
while IFS= read -r branch; do
    if [[ "$branch" == "$current_branch" ]]; then
        echo "  🟢 $branch  (AKTUALNY)"
    else
        echo "  - $branch"
    fi
done <<< "$local_branches"

echo ""
echo "🌍 **Zdalne branche na GitHub:**"
while IFS= read -r branch; do
    if ! grep -qx "$branch" <<< "$local_branches"; then
        echo "  🆕 $branch  (NOWY – tylko na zdalnym)"
    else
        echo "  - $branch"
    fi
done <<< "$remote_branches"

echo ""

# Pobranie nazwy funkcjonalności do pobrania
read -p "Podaj nazwę funkcjonalności do pobrania (branch) (ENTER = aktualny branch): " new_functionality

# Jeśli użytkownik nie podał nazwy, używamy aktualnego brancha
if [[ -z "$new_functionality" ]]; then
    new_functionality=$current_branch
    echo "🔄 Używam aktualnego brancha: $new_functionality"
else
    # Zamiana spacji na myślniki (Git nie akceptuje spacji w nazwach branchy)
    new_functionality=$(echo "$new_functionality" | tr ' ' '-')
fi

# Sprawdzenie, czy branch istnieje lokalnie
if git show-ref --verify --quiet refs/heads/"$new_functionality"; then
    echo "🟡 Przełączanie na istniejący branch '$new_functionality'..."
    git checkout "$new_functionality"
else
    echo "🟡 Tworzenie nowego brancha '$new_functionality' na podstawie zdalnego..."
    git checkout -b "$new_functionality" origin/"$new_functionality"
fi

# Pytanie o pobranie zmian
read -p "Czy chcesz pobrać najnowsze zmiany z GitHub? (Y/n): " confirm
if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
    echo "❌ Anulowano operację."
    exit 0
fi

# Pobranie najnowszych zmian
git pull origin "$new_functionality"

# Pokazanie aktualnego statusu
echo "🟢 Aktualny status repozytorium po pobraniu zmian:"
git status

echo "✅ Branch '$new_functionality' został pobrany i przełączony!"
