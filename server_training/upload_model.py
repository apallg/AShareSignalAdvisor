"""
上传模型到 HuggingFace Hub

用法:
  python upload_model.py --model-dir ./export/best_model --repo 你的账号/a-share-model
  python upload_model.py --best --repo 你的账号/a-share-model
"""
import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("upload")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default="./export/best_model", help="模型目录")
    parser.add_argument("--repo", required=True, help="HuggingFace 仓库名，如 apallg/a-share-model")
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        logger.error(f"目录不存在: {model_dir}")
        return

    try:
        from huggingface_hub import create_repo, upload_folder
    except ImportError:
        logger.error("请先安装 huggingface_hub: pip install huggingface_hub")
        return

    # 创建仓库
    create_repo(args.repo, private=args.private, exist_ok=True)
    logger.info(f"仓库: https://huggingface.co/{args.repo}")

    # 上传
    upload_folder(
        folder_path=str(model_dir),
        repo_id=args.repo,
        commit_message="Upload trained model from 4090 server",
    )
    logger.info("上传完成!")


if __name__ == "__main__":
    main()
