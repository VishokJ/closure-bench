# literal_bitselect: openai/gpt-6-sol

Rollout `gpt-6-sol/R23/6` (/Users/vishokj/Developer/cb-probe/outputs/official/gpt-6-sol/closure-bench--openai--gpt-6-sol--null--2fc9e854/traces.jsonl:159), task R23, grade status `compile_error`. Picked as the median submission length (1537 chars) of 26 rollouts in this category for this model.

Sub-label: `None`

## Evidence

```json
{
 "categories_in_log": {
  "literal_bitselect": 1
 },
 "diagnostic": "%Error: <work>/submission/tb.sv:56:18: syntax error, unexpected '[', expecting ';'",
 "fatal_errors": 1,
 "literal": "8'h5A[",
 "source_line": "rxd = 8'h5A[i];"
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 174, input_changes 10, bound 300, witness 9a44b3b1f01aa5fd
// Formal witness for R23_recover_after_frame_error_idle (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (174 cycles), replayed on the uart_rx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic rxd = 1'd0;
  logic m_axis_tready = 1'd0;
  logic [15:0] prescale = 16'd1;
  wire  [7:0] m_axis_tdata;
  wire  m_axis_tvalid;
  wire  busy;
  wire  overrun_error;
  wire  frame_error;

  uart_rx dut (.clk(clk), .rst(rst), .rxd(rxd), .m_axis_tready(m_axis_tready), .prescale(prescale), .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error));

  initial begin
    @(negedge clk);
    rst = 1'd0;
    repeat (76) @(negedge clk);
    rxd = 1'd1;
    repeat (18) @(negedge clk);
    rxd = 1'd0;
    repeat (4) @(negedge clk);
    rxd = 1'd1;
    repeat (15) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    @(negedge clk);
    rxd = 1'd0;
    repeat (18) @(negedge clk);
    rxd = 1'd1;
    repeat (7) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (19) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps

module tb;
  localparam int BIT_CLKS = 40;  // 8 * prescale

  logic clk = 1'b0;
  logic rst = 1'b1;
  logic rxd = 1'b1;
  logic m_axis_tready = 1'b1;
  logic [15:0] prescale = 16'd5;

  wire [7:0] m_axis_tdata;
  wire m_axis_tvalid;
  wire busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk),
    .rst(rst),
    .m_axis_tdata(m_axis_tdata),
    .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy),
    .overrun_error(overrun_error),
    .frame_error(frame_error),
    .prescale(prescale)
  );

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic send_good(input logic [7:0] data);
    rxd = 1'b0;
    wait_clks(BIT_CLKS);
    for (int i = 0; i < 8; i++) begin
      rxd = data[i];
      wait_clks(BIT_CLKS);
    end
    rxd = 1'b1;
    wait_clks(BIT_CLKS);
  endtask

  initial begin
    wait_clks(4);
    rst = 1'b0;
    wait_clks(4);

    // Send eight data bits, then hold the stop bit low through its
    // midpoint sample to produce a framing error.
    rxd = 1'b0;
    wait_clks(BIT_CLKS);
    for (int i = 0; i < 8; i++) begin
      rxd = 8'h5A[i];
      wait_clks(BIT_CLKS);
    end
    rxd = 1'b0;
    wait_clks(BIT_CLKS / 2);
    rxd = 1'b1;

    // Let the receiver return to idle and remain there well over 16 clocks.
    wait_clks(100);

    // The next frame is valid and delivers the target byte.
    send_good(8'hA5);
    wait_clks(40);
    $finish;
  end
endmodule
```
