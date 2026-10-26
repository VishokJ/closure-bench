// near_miss_source: formal witness of the twin cover; depth 158, bound 300, witness e2cbdfb14fe2649b
// Formal witness for T6_twin_tvalid_rise_one_late (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (158 cycles), replayed on the uart_tx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic [7:0] s_axis_tdata = 8'd195;
  logic s_axis_tvalid = 1'd0;
  logic [15:0] prescale = 16'd1;
  wire  s_axis_tready;
  wire  txd;
  wire  busy;

  uart_tx dut (.clk(clk), .rst(rst), .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .prescale(prescale), .s_axis_tready(s_axis_tready), .txd(txd), .busy(busy));

  initial begin
    @(negedge clk);
    rst = 1'd0; s_axis_tvalid = 1'd1;
    repeat (2) @(negedge clk);
    s_axis_tvalid = 1'd0;
    repeat (7) @(negedge clk);
    s_axis_tdata = 8'd60;
    repeat (73) @(negedge clk);
    s_axis_tvalid = 1'd1;
    repeat (76) @(negedge clk);
    $finish;
  end
endmodule
