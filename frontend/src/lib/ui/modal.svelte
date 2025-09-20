<script lang="ts">
    import { X } from "@lucide/svelte";
    import { Dialog } from "bits-ui";

    export let open: boolean;

    export let overlayClass = "fixed inset-0 z-40 bg-black/70 backdrop-blur-sm";
    export let contentClass =
        "fixed top-1/2 left-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-md border border-slate-700/70 bg-slate-900/95 shadow-xl ring-1 ring-slate-700/40";
    export let headerClass = "flex items-start justify-between gap-4";
    export let headerWrapperClass = "p-4";
    export let footerClass = "";
    export let titleClass =
        "flex items-center gap-2 text-sm font-semibold tracking-wide";
    export let closeButtonClass = "text-slate-400 hover:text-slate-200";

    export let title: string | undefined = undefined;
    export let showClose: boolean = true;

    export let onOpenAutoFocus: ((e: Event) => void) | undefined = (e: Event) =>
        e.preventDefault();
    export let onCloseAutoFocus: ((e: Event) => void) | undefined = undefined;
</script>

<Dialog.Root bind:open>
    <Dialog.Portal>
        <Dialog.Overlay class={overlayClass} />
        <Dialog.Content class={contentClass} {onOpenAutoFocus} {onCloseAutoFocus}>
            {#if title !== undefined || $$slots.title || showClose}
                <div class={headerWrapperClass}>
                    <div class={headerClass}>
                        <Dialog.Title class={titleClass}>
                            <slot name="title">{title}</slot>
                        </Dialog.Title>
                        {#if showClose}
                            <Dialog.Close class={closeButtonClass} aria-label="Close">
                                <X class="inline h-3.5 w-3.5" />
                            </Dialog.Close>
                        {/if}
                    </div>
                </div>
            {/if}

            <div>
                <slot />
            </div>

            {#if $$slots.footer}
                <div class={footerClass}>
                    <slot name="footer" />
                </div>
            {/if}
        </Dialog.Content>
    </Dialog.Portal>
</Dialog.Root>
