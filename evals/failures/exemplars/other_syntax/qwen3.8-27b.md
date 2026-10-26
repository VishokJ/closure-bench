# other_syntax: qwen/qwen3.8-27b

Rollout `qwen3.8-27b/R13/7` (/Users/vishokj/Developer/cb-probe/outputs/official/qwen/closure-bench--qwen--qwen3.8-27b--null--ec46d01c/traces.jsonl:203), task R13, grade status `compile_error`. Picked as the median submission length (3160 chars) of 5 rollouts in this category for this model.

Sub-label: `decl_after_statement`

## Evidence

```json
{
 "categories_in_log": {
  "other_syntax": 1
 },
 "diagnostic": "%Error: <work>/submission/tb.sv:108:18: syntax error, unexpected IDENTIFIER, expecting \"'{\"",
 "fatal_errors": 1,
 "source_line": "int unsigned tcnt = 0;"
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 156, input_changes 8, bound 300, witness 4299d18cb9b72529
// Formal witness for R13_rx_resync_after_frame_error (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (156 cycles), replayed on the uart_rx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic rxd = 1'd0;
  logic m_axis_tready = 1'd1;
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
    repeat (80) @(negedge clk);
    rxd = 1'd1;
    repeat (8) @(negedge clk);
    rxd = 1'd0;
    repeat (10) @(negedge clk);
    rxd = 1'd1;
    repeat (6) @(negedge clk);
    rxd = 1'd0;
    repeat (18) @(negedge clk);
    rxd = 1'd1;
    repeat (7) @(negedge clk);
    rxd = 1'd0;
    repeat (9) @(negedge clk);
    rxd = 1'd1;
    repeat (18) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps

module tb;
  localparam int        CLK_PERIOD = 8;
  localparam logic [15:0] PRESCALE = 16'd5;

  logic        clk = 1'b0;
  logic        rst = 1'b0;

  logic [7:0]  s_axis_tdata  = 8'h00;
  logic        s_axis_tvalid = 1'b0;
  logic        m_axis_tready = 1'b1;

  logic        rxd = 1'b1;
  logic [15:0] prescale = PRESCALE;

  wire         s_axis_tready;
  wire [7:0]   m_axis_tdata;
  wire         m_axis_tvalid;
  wire         txd;
  wire         tx_busy;
  wire         rx_busy;
  wire         rx_overrun_error;
  wire         rx_frame_error;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart dut (
    .clk(clk),
    .rst(rst),
    .s_axis_tdata(s_axis_tdata),
    .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .m_axis_tdata(m_axis_tdata),
    .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .txd(txd),
    .tx_busy(tx_busy),
    .rx_busy(rx_busy),
    .rx_overrun_error(rx_overrun_error),
    .rx_frame_error(rx_frame_error),
    .prescale(prescale)
  );

  task automatic wait_neg(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic do_reset();
    rst = 1'b0; wait_neg(2);
    rst = 1'b1; wait_neg(2);
    rst = 1'b0; wait_neg(2);
  endtask

  // The receiver samples a bit on the posedge after this condition.
  // bit_cnt: 10 = start check, 9..2 = data bits, 1 = stop bit.
  task automatic wait_rx_sample_ctl(input int K);
    forever begin
      @(negedge clk);
      if (dut.uart_rx_inst.prescale_reg == 19'd1 && dut.uart_rx_inst.bit_cnt == 4'(K)) begin
        return;
      end
    end
  endtask

  // Assumes the frame has already started and the start bit is low.
  // Drives LSB-first data bits and the stop bit at the correct sample points.
  task automatic drive_rx_bits(input logic [7:0] data, input logic stop_bit);
    for (int K = 9; K >= 2; K--) begin
      wait_rx_sample_ctl(K);
      rxd = (data >> (9 - K)) & 1'b1;
    end
    wait_rx_sample_ctl(1);
    rxd = stop_bit;
  endtask

  initial begin
    do_reset();
    wait_neg(5);
```
