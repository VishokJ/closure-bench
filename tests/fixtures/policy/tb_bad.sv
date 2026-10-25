// Every construct the testbench denylist rejects, plus a hierarchical read (allowed).
`timescale 1ns / 1ps
module tb;
  logic clk = 0;
  logic [7:0] mem [0:3];
  logic [8*8-1:0] line;
  integer fd, r;
  uart_rx #(.DATA_WIDTH(8)) dut (.clk(clk), .rst(1'b0), .m_axis_tdata(), .m_axis_tvalid(),
    .m_axis_tready(1'b1), .rxd(1'b1), .busy(), .overrun_error(), .frame_error(), .prescale(16'd1));
  always #1 clk = ~clk;
  initial begin
    force dut.frame_error_reg = 1;
    release dut.frame_error_reg;
    dut.rxd_reg = 0;
    r = $system("true");
    $system("true");
    $c("int x = 0;");
    r = $c("1");
    fd = $fopen("x.txt", "w");
    $fdisplay(fd, "x");
    $fwrite(fd, "x");
    r = $fgets(line, fd);
    r = $fscanf(fd, "%d", r);
    $fclose(fd);
    $readmemh("m.hex", mem);
    $writememh("w.hex", mem);
    $dumpfile("x.vcd");
    if (dut.frame_error_reg) $display("hierarchical read is allowed");
    #10 $finish;
  end
endmodule
