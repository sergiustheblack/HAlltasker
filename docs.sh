#!/bin/bash

# Останавливать выполнение при любой ошибке
set -e

# Настройки
SOURCE_BRANCH="architecture-v2"
TARGET_BRANCH="main"
NEW_BRANCH="docs-only-from-${SOURCE_BRANCH}"

# Выберите режим работы:
# "mr"   - создать новую ветку с этими коммитами (для последующего MR)
# "main" - сделать cherry-pick напрямую в ветку main
ACTION="mr" 

echo "🔍 Анализ коммитов между веками '$TARGET_BRANCH' и '$SOURCE_BRANCH'..."

# Убедимся, что мы находимся в актуальном репозитории и ветки доступны
git fetch origin

# Получаем список коммитов в хронологическом порядке (от старых к новым)
COMMITS=$(git log "origin/$TARGET_BRANCH..origin/$SOURCE_BRANCH" --format="%H" --reverse)

VALID_COMMITS=()

for commit in $COMMITS; do
    # Получаем список измененных файлов в конкретном коммите
    files=$(git diff-tree --no-commit-id --name-only -r "$commit")
    
    only_docs=true
    while IFS= read -r file; do
        # Проверяем, что файл начинается с docs/ или ./docs/
        if [[ ! "$file" =~ ^docs/ ]] && [[ ! "$file" =~ ^\./docs/ ]] && [[ -n "$file" ]]; then
            only_docs=false
            break
        fi
    done <<< "$files"

    # Если в коммите были изменения и все они относятся только к docs/
    if [ "$only_docs" = true ] && [ -n "$files" ]; then
        VALID_COMMITS+=("$commit")
        commit_msg=$(git log -1 --format='%s' "$commit")
        echo "  ✅ Подходящий коммит: ${commit:0:7} — $commit_msg"
    fi
done

if [ ${#VALID_COMMITS[@]} -eq 0 ]; then
    echo "❌ Не найдено коммитов, в которых изменялась *только* директория docs."
    exit 0
fi

echo ""
echo "✨ Найдено подходящих коммитов: ${#VALID_COMMITS[@]}"

if [ "$ACTION" = "main" ]; then
    echo "🔀 Режим: перенос коммитов напрямую в ветку '$TARGET_BRANCH'..."
    git checkout "$TARGET_BRANCH"
    git pull origin "$TARGET_BRANCH"
    
    for commit in "${VALID_COMMITS[@]}"; do
        echo "Применяем cherry-pick коммита $commit..."
        git cherry-pick "$commit" || { 
            echo "⚠️ Конфликт при cherry-pick коммита $commit!"
            echo "Разрешите конфликт, выполните 'git cherry-pick --continue', а затем продолжите."
            exit 1 
        }
    done
    echo "🎉 Готово! Все коммиты успешно перенесены в '$TARGET_BRANCH'."

else
    echo "🌿 Режим: создание новой ветки '$NEW_BRANCH' для Merge Request..."
    
    # Создаем новую ветку на основе актуального main
    #git checkout "$TARGET_BRANCH"
    #git pull origin "$TARGET_BRANCH"
    git switch --orphan "$NEW_BRANCH"
    
    for commit in "${VALID_COMMITS[@]}"; do
        echo "Cherry-pick коммита $commit в новую ветку..."
        git cherry-pick "$commit" || { 
            echo "⚠️ Конфликт при cherry-pick коммита $commit!"
            echo "Разрешите конфликт, выполните 'git cherry-pick --continue', а затем запустите скрипт заново или продолжите вручную."
            exit 1 
        }
    done
    
    echo ""
    echo "🎉 Готово! Создана ветка '$NEW_BRANCH' со всеми отфильтрованными коммитами."
    echo "Чтобы отправить её в удаленный репозиторий и создать MR, выполните:"
    echo "  git push -u origin $NEW_BRANCH"
fi
