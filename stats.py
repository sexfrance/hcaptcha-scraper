import os
from logmagix import Logger

log = Logger()
OUTPUT_DIR = "output"

def get_stats():
    if not os.path.exists(OUTPUT_DIR):
        log.warning("Output directory does not exist.")
        return

    stats = {}
    total_images = 0
    total_questions = 0
    total_types = 0

    for type_dir in os.listdir(OUTPUT_DIR):
        type_path = os.path.join(OUTPUT_DIR, type_dir)
        if os.path.isdir(type_path):
            total_types += 1
            stats[type_dir] = {}
            type_images = 0
            type_questions = 0
            for question_dir in os.listdir(type_path):
                question_path = os.path.join(type_path, question_dir)
                if os.path.isdir(question_path):
                    images = [f for f in os.listdir(question_path) if os.path.isfile(os.path.join(question_path, f)) and f.endswith('.png')]
                    count = len(images)
                    stats[type_dir][question_dir] = count
                    type_images += count
                    type_questions += 1
                    total_questions += 1
            stats[type_dir]['_total_images'] = type_images
            stats[type_dir]['_total_questions'] = type_questions
            total_images += type_images

    return stats, total_types, total_questions, total_images

def print_stats():
    stats, total_types, total_questions, total_images = get_stats()
    if not stats:
        return

    log.info("=== HCAPTCHA DATASET STATISTICS ===")
    log.info(f"Total Challenge Types: {total_types}")
    log.info(f"Total Questions: {total_questions}")
    log.info(f"Total Images: {total_images}")
    log.info("")

    for challenge_type, data in stats.items():
        log.info(f"Challenge Type: {challenge_type}")
        log.info(f"  Questions: {data['_total_questions']}")
        log.info(f"  Images: {data['_total_images']}")
        for question, count in data.items():
            if not question.startswith('_'):
                log.info(f"    - {question}: {count} images")
        log.info("")

if __name__ == "__main__":
    print_stats()