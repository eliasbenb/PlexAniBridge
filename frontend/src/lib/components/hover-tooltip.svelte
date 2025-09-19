<script lang="ts">
    import { onMount } from "svelte";

    export let outDelay = 100; // ms
    export let widthClass = "w-min";
    export let title: string | null = null;
    export let side: "auto" | "left" | "right" = "auto";

    let visible = false;
    let hideTimer: number | null = null;
    let wrapperEl: HTMLDivElement;
    let tipEl: HTMLDivElement;
    const tooltipId = `tooltip-${Math.random().toString(36).slice(2)}`;

    function clearTimer() {
        if (hideTimer !== null) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
    }

    function show() {
        clearTimer();
        visible = true;
        queueMicrotask(position);
    }

    function hideSoon() {
        clearTimer();
        hideTimer = window.setTimeout(() => {
            visible = false;
        }, outDelay);
    }

    function position() {
        if (!wrapperEl || !tipEl) return;
        const rect = wrapperEl.getBoundingClientRect();
        const margin = 8; // viewport margin in px

        tipEl.style.left = "0px";
        tipEl.style.right = "auto";

        const tipWidth = tipEl.getBoundingClientRect().width;
        let useRight = false;

        if (side === "right") useRight = true;
        else if (side === "left") useRight = false;
        else useRight = rect.left + tipWidth > window.innerWidth - margin;

        if (useRight) {
            tipEl.style.left = "auto";
            tipEl.style.right = "0px";
        } else {
            tipEl.style.left = "0px";
            tipEl.style.right = "auto";
        }
    }

    function onMouseEnter() {
        show();
    }
    function onMouseLeave() {
        hideSoon();
    }

    function onFocus() {
        show();
    }
    function onBlur() {
        hideSoon();
    }
    function onKeydown(e: KeyboardEvent) {
        if (e.key === "Escape") {
            e.stopPropagation();
            clearTimer();
            visible = false;
        }
    }

    onMount(() => {
        const onResize = () => {
            if (visible) position();
        };
        window.addEventListener("resize", onResize);
        return () => {
            window.removeEventListener("resize", onResize);
            clearTimer();
        };
    });
</script>

<div
    bind:this={wrapperEl}
    class="relative inline-block"
    on:mouseenter={onMouseEnter}
    on:mouseleave={onMouseLeave}
    on:focus={onFocus}
    on:blur={onBlur}
    on:keydown={onKeydown}
    role="button"
    tabindex="0"
    aria-haspopup="dialog"
    aria-expanded={visible}
    aria-describedby={tooltipId}
>
    <slot name="trigger"></slot>
    <div
        bind:this={tipEl}
        id={tooltipId}
        class={`absolute z-20 mt-1 rounded-md border border-slate-800/70 bg-slate-900/95 p-2 shadow-xl transition-opacity ${widthClass}`}
        class:opacity-100={visible}
        class:opacity-0={!visible}
        class:visible
        class:invisible={!visible}
    >
        {#if title}
            <div class="mb-1 text-[10px] font-medium text-slate-400">{title}</div>
        {/if}
        <slot></slot>
    </div>
</div>

<style>
    .opacity-0 {
        opacity: 0;
    }
    .opacity-100 {
        opacity: 1;
    }
    .transition-opacity {
        transition-property: opacity, visibility;
        transition-duration: 150ms;
    }
</style>
