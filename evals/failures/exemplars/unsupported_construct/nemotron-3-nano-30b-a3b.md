# unsupported_construct: nvidia/nemotron-3-nano-30b-a3b

Rollout `nemotron-3-nano-30b-a3b/T12/2` (/Users/vishokj/Developer/cb-probe/outputs/official/nemotron/closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b/traces.jsonl:89), task T12, grade status `compile_error`. Picked as the median submission length (3167 chars) of 9 rollouts in this category for this model.

Sub-label: `Unsupported: Unclocked assertion`

## Evidence

```json
{
 "categories_in_log": {
  "unsupported_construct": 2
 },
 "diagnostic": "%Error-UNSUPPORTED: <work>/submission/tb.sv:86:11: Unsupported: Unclocked assertion",
 "fatal_errors": 2,
 "source_line": "wait ($fell(busy) && $rose(s_axis_tready));"
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 166, input_changes 3, bound 300, witness 42b840eea11fd4a4
// Formal witness for T12_tx_b2b_busy_fall_ready_rise_9 (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (166 cycles), replayed on the uart_tx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic [7:0] s_axis_tdata = 8'd0;
  logic s_axis_tvalid = 1'd0;
  logic [15:0] prescale = 16'd1;
  wire  s_axis_tready;
  wire  txd;
  wire  busy;

  uart_tx dut (.clk(clk), .rst(rst), .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .prescale(prescale), .s_axis_tready(s_axis_tready), .txd(txd), .busy(busy));

  initial begin
    @(negedge clk);
    rst = 1'd0; s_axis_tvalid = 1'd1;
    repeat (83) @(negedge clk);
    s_axis_tvalid = 1'd0;
    repeat (83) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
module tb;
  // ------------------------------------------------------------
  // Clock and reset
  // ------------------------------------------------------------
  logic        clk;
  logic        rst;
  logic [15:0] prescale_val;
  logic [7:0]  s_axis_tdata;
  logic        s_axis_tvalid;
  logic        s_axis_tready;
  logic        busy;
  logic        txd;

  // ------------------------------------------------------------
  // DUT instantiation (uart_tx, default parameter DATA_WIDTH=8)
  // ------------------------------------------------------------
  uart_tx #(.DATA_WIDTH(8)) dut (
    .clk          (clk),
    .rst          (rst),
    .s_axis_tdata (s_axis_tdata),
    .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .txd          (txd),
    .busy         (busy),
    .prescale     (prescale_val)
  );

  // ------------------------------------------------------------
  // Clock generation (125 MHz, period = 8 ns)
  // ------------------------------------------------------------
  initial clk = 0;
  always #4 clk = ~clk;

  // ------------------------------------------------------------
  // Reset sequencing
  // ------------------------------------------------------------
  initial begin
    rst         = 0;
    prescale_val = 16'd1;
    #10 rst = 1;
    #20 rst = 0;
    #20;
  end

  // ------------------------------------------------------------
  // Helper tasks
  // ------------------------------------------------------------
  // Wait until s_axis_tready is high (idle state)
  task automatic wait_axis_tready_high();
    wait (s_axis_tready);
    @(posedge clk);
  endtask

  // Send one AXI‑Stream word (assert s_axis_tvalid for one cycle)
  task automatic send_word(input logic [7:0] data);
    // Wait for idle
    wait_axis_tready_high();
    // Present data and assert valid
    s_axis_tdata  = data;
    @(posedge clk);
    s_axis_tvalid = 1'b1;
    @(posedge clk);
    s_axis_tvalid = 1'b0;
  endtask

  // ------------------------------------------------------------
  // Main stimulus
  // ------------------------------------------------------------
  initial begin
    // Wait for reset de‑assertion
    @(negedge rst);

    // ----- First word -------------------------------------------------
    send_word(8'hA5);                     // launch first transmission
    // Wait until transmission finishes (busy goes low)
    wait (!busy);
    #10;                                  // small stabilization margin

    // ----- Second word (back‑to‑back) ---------------------------------
    send_word(8'h3C);                     // launch second transmission
```
