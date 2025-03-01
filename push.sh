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
    echo "Skrypt tworzy (lub przełącza się na) nowy branch w formacie app-X.Y.Z,"
    echo "wykonuje commit i push do origin."
    echo
    echo "Opcje:"
    echo "  --help                 Wyświetla tę pomoc"
    echo "  --major                Podbija wersję MAJOR (X -> X+1, Y=0, Z=0)"
    echo "  --minor                Podbija wersję MINOR (Y -> Y+1)"
    echo "  --patch                Podbija wersję PATCH (Z -> Z+1)"
    echo "  --message \"tekst\"      Ustawia własny komunikat commita"
    exit 0
}

###################################
# Sprawdzenie, czy to repo Git
###################################
function check_if_git_repo() {
    if [[ ! -d .git ]]; then
        echo -e "${RED}[ERROR] Nie znaleziono katalogu .git. Przerywam...${NC}"
        exit 1
    fi
}

###################################
# Sprawdzenie zmian lokalnych
###################################
function check_uncommitted_changes() {
    if [[ -n "$(git status --porcelain)" ]]; then
        echo -e "${YELLOW}[WARNING] Masz niezacommitowane zmiany. Czy na pewno kontynuować? (Y/n)${NC}"
        read -r response
        if [[ "$response" != "Y" && "$response" != "y" ]]; then
            echo -e "${RED}[ERROR] Operacja przerwana.${NC}"
            exit 1
        fi
    fi
}

###################################
# Parsowanie argumentów
###################################
user_change_type=""      # major / minor / patch / (puste)
custom_commit_message="" # jeśli ktoś poda --message
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help)
            print_help
            ;;
        --major)
            user_change_type="major"
            shift
            ;;
        --minor)
            user_change_type="minor"
            shift
            ;;
        --patch)
            user_change_type="patch"
            shift
            ;;
        --message)
            custom_commit_message="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}[ERROR] Nieznana opcja: $1${NC}"
            exit 1
            ;;
    esac
done

###################################
# Wywołanie funkcji sprawdzających
###################################
check_if_git_repo
check_uncommitted_changes

###################################
# Pobranie aktualnego brancha
###################################
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo -e "${BLUE}[INFO] Aktualnie pracujesz w branchu: ${NC}${YELLOW}$current_branch${NC}"

# Pobranie najnowszych branchy
git fetch --all --prune
latest_version=$(git branch -r | grep -Eo 'app-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/origin\///' | sort -V | tail -n 1)

if [[ -z "$latest_version" ]]; then
    latest_version="app-1.0.0"
fi

echo -e "${BLUE}[INFO] Najnowsza wersja w repo: ${NC}${GREEN}$latest_version${NC}"

version_number=$(echo "$latest_version" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+')
major=$(echo "$version_number" | cut -d. -f1)
minor=$(echo "$version_number" | cut -d. -f2)
patch=$(echo "$version_number" | cut -d. -f3)

###################################
# Funkcja pytająca użytkownika o MAJOR/MINOR/PATCH
###################################
function ask_for_change_type_if_needed() {
    if [[ -z "$user_change_type" ]]; then
        echo -e "${BLUE}[INFO] Jak duża jest zmiana?${NC}"
        echo "1) Duża (MAJOR)"
        echo "2) Średnia (MINOR)"
        echo "3) Mała (PATCH)"
        read -p "Wybierz (1/2/3): " choice
        case "$choice" in
            1) user_change_type="major" ;;
            2) user_change_type="minor" ;;
            3) user_change_type="patch" ;;
            *) 
                echo -e "${RED}[ERROR] Niepoprawny wybór. Przerywam.${NC}"
                exit 1
                ;;
        esac
    fi
}

###################################
# Funkcja ustalająca nową wersję
###################################
function determine_new_version() {
    case "$user_change_type" in
        major)
            ((major++))
            minor=0
            patch=0
            ;;
        minor)
            ((minor++))
            ;;
        patch)
            ((patch++))
            ;;
        *)
            echo -e "${RED}[ERROR] Nieznany typ zmiany: $user_change_type${NC}"
            exit 1
            ;;
    esac
    new_version="app-$major.$minor.$patch"
}

ask_for_change_type_if_needed
determine_new_version

###################################
# Tu pytamy, czy na pewno kontynuować
# (zanim zmienimy branch!)
###################################
function confirm_version_change() {
    echo -e "${BLUE}[INFO] Nowa wersja to: ${NC}${GREEN}$new_version${NC}"
    read -p "Czy chcesz utworzyć/przełączyć się na ten branch? (Y/n): " confirm
    if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
        echo -e "${RED}[ERROR] Anulowano. Nie zmieniamy branchy, nie będzie inkrementacji.${NC}"
        exit 0
    fi
}

confirm_version_change

###################################
# Funkcja: przełączanie lub tworzenie brancha
###################################
function create_or_switch_branch() {
    # Sprawdzamy, czy branch istnieje na origin
    if git ls-remote --exit-code origin "$new_version" &>/dev/null; then
        echo -e "${YELLOW}[WARNING] Branch '$new_version' istnieje już na origin. Przełączamy się...${NC}"
        # Lokalnie istnieje?
        if git show-ref --verify --quiet refs/heads/"$new_version"; then
            git checkout "$new_version"
        else
            git checkout -b "$new_version" origin/"$new_version"
        fi
    else
        # Nie istnieje na origin
        if git show-ref --verify --quiet refs/heads/"$new_version"; then
            echo -e "${YELLOW}[WARNING] Branch '$new_version' istnieje lokalnie. Przełączam się na niego.${NC}"
            git checkout "$new_version"
        else
            echo -e "${BLUE}[INFO] Tworzę nowy branch '$new_version' lokalnie.${NC}"
            git checkout -b "$new_version"
        fi
    fi
}

create_or_switch_branch

###################################
# Funkcja: commit
###################################
function git_add_commit() {
    echo -e "${YELLOW}[WARNING] Status repozytorium:${NC}"
    git status

    read -p "Czy chcesz dodać wszystkie zmiany i kontynuować? (Y/n): " confirm
    if [[ "$confirm" != "Y" && "$confirm" != "y" ]]; then
        echo -e "${RED}[ERROR] Operacja anulowana.${NC}"
        exit 0
    fi

    git add .

    # domyślny message, jeśli nie ma custom
    if [[ -z "$custom_commit_message" ]]; then
        case "$user_change_type" in
            major) custom_commit_message="Big changes" ;;
            minor) custom_commit_message="New functionalities" ;;
            patch) custom_commit_message="Bug fixes" ;;
        esac
    fi

    # Opcja nadpisania
    echo -e "${BLUE}[INFO] Domyślny commit message: '${GREEN}$custom_commit_message${NC}'"
    read -p "Podaj nowy opis (ENTER, aby zostawić): " user_msg
    commit_message=${user_msg:-$custom_commit_message}

    git commit -m "$commit_message"
}

git_add_commit

###################################
# Funkcja: pytanie o tag
###################################
function create_tag() {
    echo -e "${BLUE}[INFO] Czy utworzyć tag 'v$major.$minor.$patch'? (Y/n)${NC}"
    read -r resp
    if [[ "$resp" == "Y" || "$resp" == "y" ]]; then
        local tagname="v$major.$minor.$patch"
        git tag -a "$tagname" -m "Release $tagname"
        git push origin "$tagname"
        echo -e "${GREEN}[INFO] Tag '$tagname' został utworzony i wypchnięty.${NC}"
    fi
}

create_tag

###################################
# Funkcja: push nowego brancha
###################################
function push_branch() {
    echo -e "${BLUE}[INFO] Wypycham branch '$new_version' na GitHub...${NC}"
    git push --set-upstream origin "$new_version"
    echo -e "${GREEN}[INFO] Branch '$new_version' został wypchnięty na GitHub!${NC}"
}

push_branch
