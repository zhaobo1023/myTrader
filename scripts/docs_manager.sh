#!/bin/bash
# myTrader 文档管理脚本
# 用于自动生成和维护文档索引

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 目录定义
DOCS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docs"
INDEX_FILE="$DOCS_DIR/index.md"
README_FILE="$DOCS_DIR/README.md"

echo -e "${BLUE}=== myTrader 文档管理工具 ===${NC}\n"

# 函数：显示帮助
show_help() {
    cat << EOF
用法: $0 [选项]

选项:
    -h, --help          显示此帮助信息
    -l, --list          列出所有文档
    -s, --stats         显示文档统计信息
    -c, --check         检查文档链接有效性
    -u, --update        更新文档索引
    -f, --find KEYWORD  搜索文档
    -n, --new TITLE     创建新文档模板

示例:
    $0 --list           # 列出所有文档
    $0 --stats          # 显示统计信息
    $0 --find 微盘      # 搜索包含"微盘"的文档
    $0 --new "新功能设计"  # 创建新文档

EOF
}

# 函数：列出所有文档
list_docs() {
    echo -e "${GREEN}所有文档列表:${NC}\n"

    # 主目录文档
    echo -e "${YELLOW}主目录文档:${NC}"
    find "$DOCS_DIR" -maxdepth 1 -name "*.md" -not -name "index.md" -not -name "README.md" | sort | while read -r file; do
        filename=$(basename "$file")
        size=$(du -h "$file" | cut -f1)
        mtime=$(stat -c "%y" "$file" | cut -d' ' -f1)
        title=$(head -1 "$file" | sed 's/^#* //')
        printf "  %-40s %s | %s\n" "$filename" "[$mtime]" "$title"
    done

    # plans子目录文档
    echo -e "\n${YELLOW}详细实施计划 (plans/):${NC}"
    find "$DOCS_DIR/plans" -name "*.md" | sort | while read -r file; do
        filename=$(basename "$file")
        size=$(du -h "$file" | cut -f1)
        mtime=$(stat -c "%y" "$file" | cut -d' ' -f1)
        printf "  %-40s %s\n" "$filename" "[$mtime]"
    done
}

# 函数：显示文档统计
show_stats() {
    echo -e "${GREEN}文档统计信息:${NC}\n"

    total_docs=$(find "$DOCS_DIR" -name "*.md" -not -name "index.md" -not -name "README.md" | wc -l)
    total_size=$(du -sh "$DOCS_DIR" | cut -f1)
    main_docs=$(find "$DOCS_DIR" -maxdepth 1 -name "*.md" -not -name "index.md" -not -name "README.md" | wc -l)
    plans_docs=$(find "$DOCS_DIR/plans" -name "*.md" 2>/dev/null | wc -l)

    echo "总文档数: $total_docs"
    echo "总大小: $total_size"
    echo "主目录文档: $main_docs"
    echo "实施计划文档: $plans_docs"

    # 最新文档
    echo -e "\n${YELLOW}最近更新的5篇文档:${NC}"
    find "$DOCS_DIR" -name "*.md" -not -name "index.md" -not -name "README.md" -type f -printf '%T@ %p\n' | \
        sort -rn | head -5 | cut -d' ' -f2- | while read -r file; do
        filename=$(basename "$file")
        mtime=$(stat -c "%y" "$file" | cut -d' ' -f1)
        printf "  %-35s %s\n" "$filename" "[$mtime]"
    done

    # 文档大小排名
    echo -e "\n${YELLOW}最大的5篇文档:${NC}"
    find "$DOCS_DIR" -name "*.md" -not -name "index.md" -not -name "README.md" -type f -exec du -h {} \; | \
        sort -rh | head -5 | while read -r size file; do
        filename=$(basename "$file")
        printf "  %-35s %s\n" "$filename" "$size"
    done
}

# 函数：检查文档链接
check_links() {
    echo -e "${GREEN}检查文档链接...${NC}\n"

    # 检查相对链接
    find "$DOCS_DIR" -name "*.md" -not -name "index.md" -not -name "README.md" -exec grep -H '\[.*\](' {} \; | \
        grep -E '\([a-zA-Z_]' | while read -r line; do
        file=$(echo "$line" | cut -d':' -f1)
        link=$(echo "$line" | grep -oP '(?<=\()[^)]+' | head -1)

        # 检查是否是相对路径链接
        if [[ ! "$link" =~ ^http ]] && [[ ! "$link" =~ ^# ]]; then
            target_dir=$(dirname "$file")
            target_file="$target_dir/$link"

            if [[ ! -f "$target_file" ]]; then
                echo -e "${RED}✗${NC} $(basename "$file") -> $link (链接失效)"
            fi
        fi
    done

    echo -e "\n${GREEN}链接检查完成${NC}"
}

# 函数：搜索文档
find_docs() {
    local keyword="$1"
    echo -e "${GREEN}搜索包含 '$keyword' 的文档:${NC}\n"

    grep -r -l --include="*.md" "$keyword" "$DOCS_DIR" --exclude-dir=.git | while read -r file; do
        filename=$(basename "$file")
        # 获取包含关键词的行
        matches=$(grep -i -n --color=never "$keyword" "$file" | head -3)
        echo -e "${YELLOW}$filename${NC}"
        echo "$matches" | sed 's/^/  /'
        echo ""
    done
}

# 函数：创建新文档
new_doc() {
    local title="$1"
    if [[ -z "$title" ]]; then
        echo -e "${RED}错误: 请提供文档标题${NC}"
        echo "用法: $0 --new '文档标题'"
        exit 1
    fi

    # 生成文件名（转换为小写并替换空格为下划线）
    filename=$(echo "$title" | tr '[:upper:]' '[:lower:]' | tr ' ' '_').md
    filepath="$DOCS_DIR/$filename"

    if [[ -f "$filepath" ]]; then
        echo -e "${RED}错误: 文档已存在: $filename${NC}"
        exit 1
    fi

    # 创建文档模板
    cat > "$filepath" << EOF
# $title

**文档版本:** v1.0
**更新时间:** $(date +%Y-%m-%d)
**维护者:** $(git config user.name 2>/dev/null || echo "作者名")

---

## 一、概述
简要说明文档目的和内容

## 二、主要内容
详细内容...

## 三、总结
总结性内容

---

**文档结束**
EOF

    echo -e "${GREEN}✓${NC} 新文档已创建: $filename"
    echo "  路径: $filepath"
    echo "  请编辑文档内容"
}

# 主函数
main() {
    if [[ $# -eq 0 ]]; then
        show_help
        exit 0
    fi

    case "$1" in
        -h|--help)
            show_help
            ;;
        -l|--list)
            list_docs
            ;;
        -s|--stats)
            show_stats
            ;;
        -c|--check)
            check_links
            ;;
        -u|--update)
            echo -e "${YELLOW}提示: 文档索引由人工维护，请手动更新 index.md${NC}"
            ;;
        -f|--find)
            if [[ -z "$2" ]]; then
                echo -e "${RED}错误: 请提供搜索关键词${NC}"
                exit 1
            fi
            find_docs "$2"
            ;;
        -n|--new)
            new_doc "$2"
            ;;
        *)
            echo -e "${RED}错误: 未知选项 '$1'${NC}"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
