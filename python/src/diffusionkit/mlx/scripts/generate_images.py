# reference: https://github.com/ml-explore/mlx-examples/tree/main/stable_diffusion

# For licensing see accompanying LICENSE.md file.
# Copyright (C) 2024 Argmax, Inc. All Rights Reserved.
#

import argparse

from argmaxtools.utils import get_logger
from diffusionkit.mlx import MMDIT_CKPT, DiffusionPipeline, FluxPipeline

logger = get_logger(__name__)

# Defaults
HEIGHT = {
    "argmaxinc/mlx-stable-diffusion-3-medium": 512,
    "argmaxinc/mlx-stable-diffusion-3.5-large": 1024,
    "argmaxinc/mlx-stable-diffusion-3.5-large-4bit-quantized": 1024,
    "argmaxinc/mlx-FLUX.1-schnell": 512,
    "argmaxinc/mlx-FLUX.1-schnell-4bit-quantized": 512,
    "argmaxinc/mlx-FLUX.1-dev": 512,
}
WIDTH = {
    "argmaxinc/mlx-stable-diffusion-3-medium": 512,
    "argmaxinc/mlx-stable-diffusion-3.5-large": 1024,
    "argmaxinc/mlx-stable-diffusion-3.5-large-4bit-quantized": 1024,
    "argmaxinc/mlx-FLUX.1-schnell": 512,
    "argmaxinc/mlx-FLUX.1-schnell-4bit-quantized": 512,
    "argmaxinc/mlx-FLUX.1-dev": 512,
}
SHIFT = {
    "argmaxinc/mlx-stable-diffusion-3-medium": 3.0,
    "argmaxinc/mlx-stable-diffusion-3.5-large": 3.0,
    "argmaxinc/mlx-stable-diffusion-3.5-large-4bit-quantized": 3.0,
    "argmaxinc/mlx-FLUX.1-schnell": 1.0,
    "argmaxinc/mlx-FLUX.1-schnell-4bit-quantized": 1.0,
    "argmaxinc/mlx-FLUX.1-dev": 1.0,
}


def cli():
    parser = argparse.ArgumentParser(
        description="Generate images from a text (and an optional image) prompt using Stable Diffusion"
    )
    parser.add_argument("--prompt", required=True, help="Text prompt")
    parser.add_argument(
        "--image-path", type=str, help="Path to the image prompt", default=None
    )
    parser.add_argument(
        "--model-version",
        choices=tuple(MMDIT_CKPT.keys()),
        default="argmaxinc/mlx-FLUX.1-schnell",
        help="Diffusion model version, e.g. FLUX-1.schnell, stable-diffusion-3-medium",
    )
    parser.add_argument(
        "--steps", type=int, default=50, help="Number of diffusion steps."
    )
    parser.add_argument(
        "--cfg",
        type=float,
        default=5.0,
        help="Classifier-free guidance weight",
    )
    parser.add_argument("--negative_prompt", default="", help="Negative text prompt")
    parser.add_argument(
        "--preload-models",
        action="store_true",
        help="Preload the models in memory. Default version lazy loads the models.",
    )
    parser.add_argument(
        "--output-path", "-o", default="out.png", help="Path to save the output image."
    )
    parser.add_argument(
        "--seed", type=int, help="Seed for the random number generator."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed information."
    )
    parser.add_argument(
        "--shift",
        type=float,
        help="Shift for diffusion sampling",
    )
    parser.add_argument(
        "--t5",
        action="store_true",
        help="Engages T5 for stronger text embeddings (uses significantly more memory). ",
    )
    parser.add_argument("--height", type=int, help="Height of the output image")
    parser.add_argument("--width", type=int, help="Width of the output image")
    parser.add_argument(
        "--no-low-memory-mode",
        action="store_false",
        dest="low_memory_mode",
        help="Disable low memory mode: No models offloading",
    )
    parser.add_argument(
        "--benchmark-mode",
        action="store_true",
        help="Run the script in benchmark mode (no memory cleanup).",
    )
    parser.add_argument(
        "--denoise",
        type=float,
        default=0.0,
        help="Denoising factor when an input image is provided. (between 0.0 and 1.0)",
    )
    parser.add_argument(
        "--local-ckpt",
        default=None,
        type=str,
        help="Path to the local mmdit checkpoint.",
    )

    args = parser.parse_args()

    args.w16 = True
    args.a16 = True

    if "FLUX" in args.model_version and args.cfg > 0.0:
        logger.warning(f"Disabling CFG for {args.model_version} model.")
        args.cfg = 0.0

    if args.benchmark_mode:
        if args.low_memory_mode:
            logger.warning("Benchmark mode is enabled, disabling low memory mode.")
        args.low_memory_mode = False

    if args.denoise < 0.0 or args.denoise > 1.0:
        raise ValueError("Denoising factor must be between 0.0 and 1.0")

    shift = args.shift or SHIFT[args.model_version]
    pipeline_class = FluxPipeline if "FLUX" in args.model_version else DiffusionPipeline

    # Load the models
    sd = pipeline_class(
        w16=args.w16,
        shift=shift,
        use_t5=args.t5,
        model_version=args.model_version,
        low_memory_mode=args.low_memory_mode,
        a16=args.a16,
        local_ckpt=args.local_ckpt,
    )

    # Ensure that models are read in memory if needed
    if args.preload_models:
        sd.ensure_models_are_loaded()

    height = args.height or HEIGHT[args.model_version]
    width = args.width or WIDTH[args.model_version]
    assert height % 16 == 0, f"Height must be divisible by 16 ({height}/16={height/16})"
    assert width % 16 == 0, f"Width must be divisible by 16 ({width}/16={width/16})"
    logger.info(f"Output image resolution will be {height}x{width}")

    if args.benchmark_mode:
        args.low_memory_mode = False
        sd.ensure_models_are_loaded()
        logger.info(
            "Running in benchmark mode. Warming up the models. (generated latents will be discarded)"
        )
        image = sd.generate_image(
            args.prompt,
            cfg_weight=args.cfg,
            num_steps=1,
            seed=args.seed,
            negative_text=args.negative_prompt,
            latent_size=(height // 8, width // 8),
            verbose=False,
        )
        logger.info("Benchmark mode: Warming up the models done.")

    # Generate the latent vectors using diffusion
    image, _ = sd.generate_image(
        args.prompt,
        cfg_weight=args.cfg,
        num_steps=args.steps,
        seed=args.seed,
        negative_text=args.negative_prompt,
        latent_size=(height // 8, width // 8),
        image_path=args.image_path,
        denoise=args.denoise,
    )

    # Save them to disc
    image.save(args.output_path)
    logger.info(f"Saved the image to {args.output_path}")


if __name__ == "__main__":
    cli()
