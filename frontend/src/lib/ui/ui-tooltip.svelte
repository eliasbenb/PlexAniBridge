<script lang="ts">
  import { Tooltip } from "bits-ui";
  export let delay = 100;
  export let contentClass =
    "z-20 w-min min-w-[8rem] rounded-md border border-slate-800/70 bg-slate-900/95 p-2 shadow-xl";
  export let sideOffset = 8;
</script>

<Tooltip.Root delayDuration={delay}>
  <Tooltip.Trigger>
    <slot name="trigger" />
  </Tooltip.Trigger>
  <Tooltip.Portal>
    <Tooltip.Content sideOffset={sideOffset} class={contentClass}>
      <slot />
      <Tooltip.Arrow />
    </Tooltip.Content>
  </Tooltip.Portal>
</Tooltip.Root>
